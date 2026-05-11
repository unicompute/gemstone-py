"""
migrations.py — Reusable Migration base class for GemStone schema migrations.

This module provides a concrete migration lifecycle for translated example
scripts and application code:
  - `up(session)`   — forward migration (v1 → v2)
  - `down(session)` — rollback (v2 → v1), optional
  - `run(session)`  — run up() with commit-conflict retry and progress logging
  - `rollback(session)` — run down() with retry

Usage
-----
    import gemstone_py as gemstone
    from gemstone_py.migrations import Migration
    from gemstone_py.persistent_root import PersistentRoot

    class AddWordCount(Migration):
        description = "Add word_count field to BlogPosts"
        chunk_size  = 50      # commit every N objects (default: 100)

        def up(self, session):
            from gemstone_py.persistent_root import PersistentRoot
            root = PersistentRoot(session)
            posts = root.get('BlogPosts') or {}
            for post_id in posts.keys():
                post = posts[post_id]
                if 'word_count' not in post.keys():
                    text = post.get('text', '')
                    post['word_count'] = str(len(text.split()))
            # run() handles committing

    with gemstone.GemStoneSession() as s:
        AddWordCount().run(s)
"""

from __future__ import annotations

PORTING_STATUS = "plain_gemstone_port"
RUNTIME_REQUIREMENT = "Works on plain GemStone images over GCI"

import argparse
import hashlib
import importlib
import inspect
import re
import textwrap
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Optional, TypeAlias

import gemstone_py as gemstone


class MigrationError(Exception):
    pass


DEFAULT_VERSION_ROOT = "GemstonePyMigrations"
MigrationCallback = Callable[[gemstone.GemStoneSession], None]


@dataclass(frozen=True)
class MigrationStep:
    """
    One module-style GemStone migration.

    A migration module can expose:

    - ``id``: stable migration id; defaults to the module basename
    - ``dependencies``: tuple/list of migration ids that must run first
    - ``description``: human-readable summary; defaults to the module docstring
    - ``upgrade(session)``: required forward migration
    - ``downgrade(session)``: optional rollback migration
    """

    id: str
    upgrade: MigrationCallback
    downgrade: MigrationCallback | None = None
    dependencies: tuple[str, ...] = ()
    checksum: str = ""
    description: str = ""
    module_name: str = ""
    source_path: Path | None = None


@dataclass(frozen=True)
class MigrationResult:
    """Result returned by ``upgrade(...)`` and ``downgrade(...)``."""

    direction: str
    target: str | None
    steps: tuple[str, ...]
    dry_run: bool = False


MigrationInput: TypeAlias = MigrationStep | ModuleType | str


def migration_id_from_module(module_name: str) -> str:
    """Return the default migration id for a module name."""
    return module_name.rsplit(".", 1)[-1]


def migration_from_module(module: ModuleType | str) -> MigrationStep:
    """Build a ``MigrationStep`` from a Python migration module."""
    loaded = importlib.import_module(module) if isinstance(module, str) else module
    upgrade_callback = getattr(loaded, "upgrade", None)
    if not callable(upgrade_callback):
        raise MigrationError(f"{loaded.__name__} does not define upgrade(session)")

    downgrade_callback = getattr(loaded, "downgrade", None)
    if downgrade_callback is not None and not callable(downgrade_callback):
        raise MigrationError(f"{loaded.__name__}.downgrade is not callable")

    dependencies = tuple(str(dep) for dep in getattr(loaded, "dependencies", ()))
    source_path = _module_source_path(loaded)
    return MigrationStep(
        id=str(getattr(loaded, "id", migration_id_from_module(loaded.__name__))),
        upgrade=upgrade_callback,
        downgrade=downgrade_callback,
        dependencies=dependencies,
        checksum=str(getattr(loaded, "checksum", "")) or _module_checksum(source_path),
        description=str(getattr(loaded, "description", inspect.getdoc(loaded) or "")),
        module_name=loaded.__name__,
        source_path=source_path,
    )


def load_manifest(manifest: ModuleType | str) -> tuple[MigrationStep, ...]:
    """
    Load migration steps from a manifest module.

    The manifest must expose ``migrations`` or ``MIGRATIONS`` containing module
    names, module objects, or ``MigrationStep`` instances.
    """
    loaded = importlib.import_module(manifest) if isinstance(manifest, str) else manifest
    entries = getattr(loaded, "migrations", None)
    if entries is None:
        entries = getattr(loaded, "MIGRATIONS", None)
    if entries is None:
        raise MigrationError(f"{loaded.__name__} does not define migrations")
    return _coerce_steps(entries)


def plan_upgrade(
    steps: Sequence[MigrationInput],
    applied: Iterable[str] | Mapping[str, object] = (),
    *,
    target: str | None = None,
) -> tuple[MigrationStep, ...]:
    """Return the pending upgrade steps in dependency-safe order."""
    ordered = _ordered_steps(_coerce_steps(steps))
    known = {step.id for step in ordered}
    if target is not None and target not in known:
        raise MigrationError(f"unknown migration target {target!r}")

    applied_ids = _applied_id_set(applied)
    pending: list[MigrationStep] = []
    for step in ordered:
        if step.id not in applied_ids:
            pending.append(step)
        if step.id == target:
            break
    return tuple(pending)


def plan_downgrade(
    steps: Sequence[MigrationInput],
    applied: Iterable[str] | Mapping[str, object],
    *,
    target: str | None = None,
) -> tuple[MigrationStep, ...]:
    """
    Return rollback steps in reverse order.

    ``target`` is kept applied. Use ``target=None`` or ``target="base"`` to
    roll back every applied migration known to the manifest.
    """
    ordered = _ordered_steps(_coerce_steps(steps))
    known = {step.id for step in ordered}
    applied_ids = _applied_id_set(applied)
    if target == "base":
        target = None
    if target is not None:
        if target not in known:
            raise MigrationError(f"unknown migration target {target!r}")
        if target not in applied_ids:
            raise MigrationError(f"migration target {target!r} is not applied")

    pending: list[MigrationStep] = []
    for step in reversed(ordered):
        if step.id not in applied_ids:
            continue
        if target is not None and step.id == target:
            break
        pending.append(step)
    return tuple(pending)


def applied_migrations(
    session: gemstone.GemStoneSession,
    *,
    root_key: str = DEFAULT_VERSION_ROOT,
) -> dict[str, dict[str, str]]:
    """Read the GemStone-side migration version table."""
    from gemstone_py.persistent_root import PersistentRoot

    root = PersistentRoot(session)
    return _normalize_applied_table(root.get(root_key))


def current_version(
    session: gemstone.GemStoneSession,
    *,
    root_key: str = DEFAULT_VERSION_ROOT,
) -> str | None:
    """Return the latest applied migration id, or ``None`` for a base stone."""
    applied = applied_migrations(session, root_key=root_key)
    if not applied:
        return None
    latest = max(
        applied.values(),
        key=lambda record: (record.get("applied_at", ""), record.get("id", "")),
    )
    return latest.get("id")


def upgrade(
    session: gemstone.GemStoneSession,
    steps: Sequence[MigrationInput],
    *,
    target: str | None = None,
    dry_run: bool = False,
    root_key: str = DEFAULT_VERSION_ROOT,
) -> MigrationResult:
    """Apply pending module-style migrations and record each committed step."""
    applied = applied_migrations(session, root_key=root_key)
    pending = plan_upgrade(steps, applied, target=target)
    if dry_run:
        return MigrationResult("upgrade", target, tuple(step.id for step in pending), True)

    for step in pending:
        try:
            step.upgrade(session)
            applied[step.id] = _applied_record(step)
            _write_applied_migrations(session, applied, root_key=root_key)
            session.commit()
        except Exception as exc:
            session.abort()
            raise MigrationError(f"failed to apply migration {step.id}") from exc
    return MigrationResult("upgrade", target, tuple(step.id for step in pending))


def downgrade(
    session: gemstone.GemStoneSession,
    steps: Sequence[MigrationInput],
    *,
    target: str | None = None,
    dry_run: bool = False,
    root_key: str = DEFAULT_VERSION_ROOT,
) -> MigrationResult:
    """Roll back applied module-style migrations down to ``target``."""
    applied = applied_migrations(session, root_key=root_key)
    pending = plan_downgrade(steps, applied, target=target)
    missing = [step.id for step in pending if step.downgrade is None]
    if missing:
        raise MigrationError(f"migration(s) do not support downgrade: {', '.join(missing)}")
    if dry_run:
        return MigrationResult("downgrade", target, tuple(step.id for step in pending), True)

    for step in pending:
        try:
            assert step.downgrade is not None
            step.downgrade(session)
            applied.pop(step.id, None)
            _write_applied_migrations(session, applied, root_key=root_key)
            session.commit()
        except Exception as exc:
            session.abort()
            raise MigrationError(f"failed to roll back migration {step.id}") from exc
    return MigrationResult("downgrade", target, tuple(step.id for step in pending))


def scaffold(
    name: str,
    directory: str | Path,
    *,
    number: int | None = None,
    dependencies: Sequence[str] = (),
) -> Path:
    """Create a numbered module-style migration file."""
    slug = _slugify(name)
    if not slug:
        raise MigrationError("migration name must contain at least one letter or digit")
    output_dir = Path(directory)
    output_dir.mkdir(parents=True, exist_ok=True)
    migration_number = number if number is not None else _next_migration_number(output_dir)
    migration_id = f"{migration_number:03d}_{slug}"
    path = output_dir / f"{migration_id}.py"
    if path.exists():
        raise MigrationError(f"migration already exists: {path}")

    deps = tuple(str(dep) for dep in dependencies)
    path.write_text(_scaffold_source(migration_id, deps), encoding="utf-8")
    return path


def build_parser() -> argparse.ArgumentParser:
    """Build the ``gemstone-migrations`` command-line parser."""
    parser = argparse.ArgumentParser(
        prog="gemstone-migrations",
        description="Helpers for gemstone-py module-style migrations.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    scaffold_parser = subcommands.add_parser("scaffold", help="Create a migration file.")
    scaffold_parser.add_argument("name", help="Migration name, e.g. add_amount_to_booking.")
    scaffold_parser.add_argument(
        "--directory",
        default="migrations",
        type=Path,
        help="Directory where the migration file should be created.",
    )
    scaffold_parser.add_argument("--number", type=int, help="Explicit numeric prefix.")
    scaffold_parser.add_argument(
        "--depends-on",
        action="append",
        default=[],
        help="Migration id dependency. Can be passed more than once.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the ``gemstone-migrations`` CLI."""
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.command == "scaffold":
        path = scaffold(
            args.name,
            args.directory,
            number=args.number,
            dependencies=tuple(args.depends_on),
        )
        print(path)
        return 0
    parser.error(f"unknown command {args.command!r}")
    return 2


def main_entry() -> None:
    """Console-script wrapper for ``gemstone-migrations``."""
    raise SystemExit(main())


def _coerce_steps(entries: Iterable[MigrationInput]) -> tuple[MigrationStep, ...]:
    steps: list[MigrationStep] = []
    for entry in entries:
        if isinstance(entry, MigrationStep):
            steps.append(entry)
        else:
            steps.append(migration_from_module(entry))
    return tuple(steps)


def _ordered_steps(steps: Sequence[MigrationStep]) -> tuple[MigrationStep, ...]:
    by_id: dict[str, MigrationStep] = {}
    for step in steps:
        if step.id in by_id:
            raise MigrationError(f"duplicate migration id {step.id!r}")
        by_id[step.id] = step

    ordered: list[MigrationStep] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(step: MigrationStep) -> None:
        if step.id in visited:
            return
        if step.id in visiting:
            raise MigrationError(f"migration dependency cycle at {step.id!r}")
        visiting.add(step.id)
        for dependency in step.dependencies:
            dependency_step = by_id.get(dependency)
            if dependency_step is None:
                raise MigrationError(
                    f"migration {step.id!r} depends on unknown migration {dependency!r}"
                )
            visit(dependency_step)
        visiting.remove(step.id)
        visited.add(step.id)
        ordered.append(step)

    for step in steps:
        visit(step)
    return tuple(ordered)


def _applied_id_set(applied: Iterable[str] | Mapping[str, object]) -> set[str]:
    if isinstance(applied, Mapping):
        return {str(key) for key in applied.keys()}
    return {str(key) for key in applied}


def _normalize_applied_table(table: object) -> dict[str, dict[str, str]]:
    if table is None:
        return {}
    if not hasattr(table, "items"):
        raise MigrationError(
            f"{DEFAULT_VERSION_ROOT} must be a mapping, got {type(table).__name__}"
        )
    result: dict[str, dict[str, str]] = {}
    for raw_key, raw_value in table.items():
        key = str(raw_key)
        if hasattr(raw_value, "items"):
            record = {str(field): str(value) for field, value in raw_value.items()}
        else:
            record = {"id": key, "checksum": str(raw_value)}
        record.setdefault("id", key)
        record.setdefault("checksum", "")
        record.setdefault("applied_at", "")
        result[key] = record
    return result


def _write_applied_migrations(
    session: gemstone.GemStoneSession,
    applied: Mapping[str, Mapping[str, str]],
    *,
    root_key: str,
) -> None:
    from gemstone_py.persistent_root import PersistentRoot

    root = PersistentRoot(session)
    root[root_key] = {
        migration_id: {
            "id": record.get("id", migration_id),
            "checksum": record.get("checksum", ""),
            "applied_at": record.get("applied_at", ""),
            "description": record.get("description", ""),
        }
        for migration_id, record in applied.items()
    }


def _applied_record(step: MigrationStep) -> dict[str, str]:
    return {
        "id": step.id,
        "checksum": step.checksum,
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "description": step.description,
    }


def _module_source_path(module: ModuleType) -> Path | None:
    filename = getattr(module, "__file__", None)
    if not filename:
        return None
    return Path(filename)


def _module_checksum(source_path: Path | None) -> str:
    if source_path is None or not source_path.exists():
        return ""
    digest = hashlib.sha256()
    digest.update(source_path.read_bytes())
    return digest.hexdigest()


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip().lower())
    return slug.strip("_")


def _next_migration_number(directory: Path) -> int:
    highest = 0
    for path in directory.glob("*.py"):
        match = re.match(r"^(\d+)_", path.name)
        if match:
            highest = max(highest, int(match.group(1)))
    return highest + 1


def _scaffold_source(migration_id: str, dependencies: tuple[str, ...]) -> str:
    return textwrap.dedent(
        f'''\
        """Migration {migration_id}."""

        from __future__ import annotations

        from gemstone_py import GemStoneSession

        id = "{migration_id}"
        dependencies = {dependencies!r}


        def upgrade(session: GemStoneSession) -> None:
            """Apply this migration."""
            raise NotImplementedError("fill in migration upgrade")


        def downgrade(session: GemStoneSession) -> None:
            """Roll back this migration."""
            raise NotImplementedError("fill in migration downgrade")
        '''
    )


class Migration:
    """
    Abstract base class for GemStone schema migrations.

    Subclasses must implement `up(session)`.  `down(session)` is optional
    (override for reversible migrations).

    Class attributes
    ----------------
    description : str
        Human-readable summary printed during run.
    chunk_size : int
        How many objects to process per commit.  Smaller values reduce
        memory pressure and conflict windows; larger values are faster.
        Default: 100.
    max_retries : int
        Maximum commit attempts before giving up (default: 10).
    """

    description: str = ''
    chunk_size:  int = 100
    max_retries: int = 10

    # ------------------------------------------------------------------
    # Subclass interface
    # ------------------------------------------------------------------

    def up(self, session: gemstone.GemStoneSession) -> None:
        """
        Apply the migration.  Called by run().

        Make changes to GemStone objects here.  Do NOT commit inside this
        method — run() handles commits with conflict retry.

        Raise MigrationError to abort.
        """
        raise NotImplementedError(
            f"{type(self).__name__}.up() is not implemented"
        )

    def down(self, session: gemstone.GemStoneSession) -> None:
        """
        Roll back the migration.  Called by rollback().

        Optional — override for reversible migrations.
        The default implementation raises MigrationError.
        """
        raise MigrationError(
            f"{type(self).__name__} does not support rollback"
        )

    # ------------------------------------------------------------------
    # Chunked iteration helper
    # ------------------------------------------------------------------

    def each_in_chunks(
        self,
        session: gemstone.GemStoneSession,
        class_name: str,
        callback: Callable[[gemstone.GemStoneSession, object], None],
        *,
        chunk_size: Optional[int] = None,
        wrap: bool = False,
    ) -> int:
        """
        Iterate over all instances of `class_name` in chunks, calling
        `callback(session, instance)` for each, committing every `chunk_size`
        objects.

        Parameters
        ----------
        session : GemStoneSession
        class_name : str
            GemStone class name (e.g. 'RcCounter').
        callback : callable(session, instance) → None
            Called for each instance. By default `instance` is a raw OOP
            integer for compatibility. With `wrap=True`, it is the same
            natural Python value or sendable proxy used by `PersistentRoot`.
        chunk_size : int, optional
            Override the class-level chunk_size for this call.
        wrap : bool, default False
            When True, iterate wrapped objects instead of raw OOP integers.

        Returns
        -------
        int
            Total number of objects processed.
        """
        from gemstone_py.concurrency import list_instances

        n = chunk_size or self.chunk_size
        instances = list_instances(session, class_name, wrap=wrap)
        total = 0
        for i, instance in enumerate(instances, 1):
            callback(session, instance)
            total += 1
            if i % n == 0:
                self._commit_with_retry(session)
                self._log(f"  committed chunk ({i}/{len(instances)})")
        if total % n != 0:
            self._commit_with_retry(session)
        return total

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def run(self, session: gemstone.GemStoneSession) -> None:
        """
        Run the migration: call up(), then commit with retry.

        Prints progress to stdout.
        """
        name = self.description or type(self).__name__
        self._log(f"[migration] {name}")
        t0 = time.monotonic()
        session.abort()        # fresh view before we start
        self.up(session)
        self._commit_with_retry(session)
        elapsed = time.monotonic() - t0
        self._log(f"[migration] done in {elapsed:.2f}s")

    def rollback(self, session: gemstone.GemStoneSession) -> None:
        """
        Roll back the migration: call down(), then commit with retry.
        """
        name = self.description or type(self).__name__
        self._log(f"[migration] rollback {name}")
        session.abort()
        self.down(session)
        self._commit_with_retry(session)
        self._log("[migration] rollback done")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _commit_with_retry(self, session: gemstone.GemStoneSession) -> None:
        """
        Commit with up to max_retries attempts on conflict.

        On a commit conflict the session's pending changes are still live
        (GciCommit returning False does not roll them back).  We simply
        abort to get a fresh server view and then retry the commit.  We do
        NOT call up() again — the changes written by up() are still present
        in the session's object space and will be included in the retry.
        """
        from gemstone_py.concurrency import CommitConflictError
        from gemstone_py.concurrency import commit as _commit
        for attempt in range(1, self.max_retries + 1):
            try:
                _commit(session)
                return
            except CommitConflictError:
                if attempt == self.max_retries:
                    raise MigrationError(
                        f"Migration commit failed after {self.max_retries} attempts"
                    )
                session.abort()
                # Do NOT re-call up() here — changes are still in the session
                # after a failed commit; abort gives us a fresh server view
                # and the next commit attempt will include them.

    @staticmethod
    def _log(msg: str) -> None:
        print(msg, flush=True)


if __name__ == "__main__":
    main_entry()
