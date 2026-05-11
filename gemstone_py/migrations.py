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
import os
import re
import socket
import textwrap
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any, Optional, TypeAlias

import gemstone_py as gemstone


class MigrationError(Exception):
    pass


DEFAULT_VERSION_ROOT = "GemstonePyMigrations"
DEFAULT_LOCK_ROOT = f"{DEFAULT_VERSION_ROOT}Lock"
DEFAULT_LOCK_STALE_AFTER_SECONDS = 60 * 60
MigrationCallback = Callable[[Any], None]


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
    operations: tuple[str, ...] = ()


@dataclass(frozen=True)
class MigrationStatus:
    """Current GemStone migration state for a manifest."""

    current: str | None
    applied: tuple[str, ...]
    pending: tuple[str, ...]


@dataclass(frozen=True)
class MigrationLock:
    """GemStone-side advisory lock record for migration runs."""

    key: str
    owner: str
    acquired_at: str
    root_key: str


class RecordingMigrationSession:
    """
    Session-like recorder used by migration dry-runs.

    It records common GemStone session calls as strings and returns harmless
    placeholders. It is intentionally limited; migrations that depend on live
    query results still need a reviewed manual dry-run.
    """

    def __init__(self) -> None:
        self.operations: list[str] = []

    def eval(self, source: str) -> None:
        self._record("eval", source)
        return None

    def eval_oop(self, source: str) -> int:
        self._record("eval_oop", source)
        return 0

    def execute(self, source: str) -> int:
        self._record("execute", source)
        return 0

    def execute_oop(self, source: str) -> int:
        self._record("execute_oop", source)
        return 0

    def perform_value(self, receiver: int, selector: str, *args: Any) -> None:
        self._record("perform_value", receiver, selector, *args)
        return None

    def perform_oop(self, receiver: int, selector: str, *args: Any) -> int:
        self._record("perform_oop", receiver, selector, *args)
        return 0

    def new_string(self, value: str) -> int:
        self._record("new_string", value)
        return 0

    def new_symbol(self, value: str) -> int:
        self._record("new_symbol", value)
        return 0

    def resolve(self, name: str) -> int:
        self._record("resolve", name)
        return 0

    def resolve_symbol(self, name: str) -> int:
        self._record("resolve_symbol", name)
        return 0

    def commit(self) -> None:
        self._record("commit")

    def abort(self) -> None:
        self._record("abort")

    def _record(self, method: str, *args: Any, **kwargs: Any) -> None:
        rendered = ", ".join(
            [*(repr(arg) for arg in args), *(f"{key}={value!r}" for key, value in kwargs.items())]
        )
        self.operations.append(f"session.{method}({rendered})")


@dataclass(frozen=True)
class ClassDiff:
    """Difference between a GemStone class and a local Python type witness."""

    class_name: str
    local_class_name: str
    remote_instvars: tuple[str, ...]
    local_instvars: tuple[str, ...]
    missing_instvars: tuple[str, ...]
    extra_instvars: tuple[str, ...]
    suggested_upgrade: tuple[str, ...]
    suggested_downgrade: tuple[str, ...]

    @property
    def is_current(self) -> bool:
        """Return ``True`` when local and remote instance variables match."""
        return not self.missing_instvars and not self.extra_instvars


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


def validate_migration_state(
    steps: Sequence[MigrationInput],
    applied: Iterable[str] | Mapping[str, object],
) -> tuple[MigrationStep, ...]:
    """
    Validate that the GemStone-side version table matches the local manifest.

    This catches two dangerous cases before applying more migrations:

    - the stone has an applied migration id that the local manifest does not know
    - an applied migration file checksum differs from the local migration module
    """
    ordered = _ordered_steps(_coerce_steps(steps))
    _check_applied_against_manifest(ordered, applied)
    return ordered


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
    return _current_version_from_applied(applied)


def migration_status(
    session: gemstone.GemStoneSession,
    steps: Sequence[MigrationInput],
    *,
    root_key: str = DEFAULT_VERSION_ROOT,
) -> MigrationStatus:
    """Return applied and pending migration ids for a live GemStone session."""
    applied = applied_migrations(session, root_key=root_key)
    ordered = validate_migration_state(steps, applied)
    pending = plan_upgrade(ordered, applied)
    latest = _current_version_from_applied(applied)
    return MigrationStatus(
        current=latest,
        applied=tuple(_applied_id_set(applied)),
        pending=tuple(step.id for step in pending),
    )


def acquire_migration_lock(
    session: gemstone.GemStoneSession,
    *,
    root_key: str = DEFAULT_VERSION_ROOT,
    lock_key: str | None = None,
    owner: str | None = None,
    stale_after_seconds: float | None = DEFAULT_LOCK_STALE_AFTER_SECONDS,
    force: bool = False,
) -> MigrationLock:
    """
    Acquire the GemStone-side advisory migration lock.

    The lock is a small record in ``UserGlobals``. Acquiring it commits once so
    other sessions see the lock before migration steps begin.
    """
    from gemstone_py.persistent_root import PersistentRoot

    resolved_key = lock_key or DEFAULT_LOCK_ROOT
    root = PersistentRoot(session)
    existing = _normalize_lock(root.get(resolved_key))
    if existing and not force and not _lock_is_stale(existing, stale_after_seconds):
        raise MigrationError(
            f"migration lock {resolved_key!r} is held by {existing.get('owner', 'unknown')}"
        )

    lock = MigrationLock(
        key=resolved_key,
        owner=owner or _default_lock_owner(),
        acquired_at=_utcnow_iso(),
        root_key=root_key,
    )
    root[resolved_key] = {
        "owner": lock.owner,
        "acquired_at": lock.acquired_at,
        "root_key": lock.root_key,
    }
    try:
        session.commit()
    except Exception as exc:
        session.abort()
        raise MigrationError(f"failed to acquire migration lock {resolved_key!r}") from exc
    return lock


def release_migration_lock(
    session: gemstone.GemStoneSession,
    lock: MigrationLock,
    *,
    force: bool = False,
) -> None:
    """Release a previously acquired GemStone-side migration lock."""
    from gemstone_py.persistent_root import PersistentRoot

    root = PersistentRoot(session)
    existing = _normalize_lock(root.get(lock.key))
    if not existing:
        return
    if not force and existing.get("owner") != lock.owner:
        raise MigrationError(
            f"migration lock {lock.key!r} is held by {existing.get('owner', 'unknown')}; "
            f"not releasing lock owned by {lock.owner!r}"
        )
    del root[lock.key]
    try:
        session.commit()
    except Exception as exc:
        session.abort()
        raise MigrationError(f"failed to release migration lock {lock.key!r}") from exc


def diff_class(
    session: gemstone.GemStoneSession,
    class_name: str | None = None,
    *,
    local_class: type[Any],
) -> ClassDiff:
    """
    Compare a GemStone class description with a local Python type witness.

    Local instance variables are inferred from annotations and ``@property``
    methods. The result is advisory: review the suggested Smalltalk before
    placing it in a real migration, especially for classes with existing data.
    """
    from gemstone_py.oop import gemstone_class_name

    remote_class_name = class_name or gemstone_class_name(local_class)
    if remote_class_name is None:
        raise MigrationError(
            "class_name is required when local_class is not decorated with @gemstone_class"
        )
    description = session.describe_class(remote_class_name)
    remote_instvars = tuple(description.instvars)
    local_instvars = _local_instvars(local_class)
    remote_set = set(remote_instvars)
    local_set = set(local_instvars)
    missing = tuple(name for name in local_instvars if name not in remote_set)
    extra = tuple(name for name in remote_instvars if name not in local_set)
    return ClassDiff(
        class_name=description.name,
        local_class_name=f"{local_class.__module__}.{local_class.__qualname__}",
        remote_instvars=remote_instvars,
        local_instvars=local_instvars,
        missing_instvars=missing,
        extra_instvars=extra,
        suggested_upgrade=tuple(
            f"session.eval({_class_instvar_source(description.name, name, add=True)!r})"
            for name in missing
        ),
        suggested_downgrade=tuple(
            f"session.eval({_class_instvar_source(description.name, name, add=False)!r})"
            for name in reversed(missing)
        ),
    )


def upgrade(
    session: gemstone.GemStoneSession,
    steps: Sequence[MigrationInput],
    *,
    target: str | None = None,
    dry_run: bool = False,
    root_key: str = DEFAULT_VERSION_ROOT,
    use_lock: bool = True,
    lock_key: str | None = None,
    lock_owner: str | None = None,
    lock_stale_after_seconds: float | None = DEFAULT_LOCK_STALE_AFTER_SECONDS,
    force_lock: bool = False,
    record_dry_run: bool = False,
) -> MigrationResult:
    """Apply pending module-style migrations and record each committed step."""
    applied = applied_migrations(session, root_key=root_key)
    ordered = validate_migration_state(steps, applied)
    pending = plan_upgrade(ordered, applied, target=target)
    if dry_run:
        operations = _record_pending_steps(pending, direction="upgrade") if record_dry_run else ()
        return MigrationResult(
            "upgrade",
            target,
            tuple(step.id for step in pending),
            True,
            operations,
        )

    lock = (
        acquire_migration_lock(
            session,
            root_key=root_key,
            lock_key=lock_key,
            owner=lock_owner,
            stale_after_seconds=lock_stale_after_seconds,
            force=force_lock,
        )
        if use_lock and pending
        else None
    )
    operation_error: BaseException | None = None
    try:
        for step in pending:
            try:
                step.upgrade(session)
                applied[step.id] = _applied_record(step)
                _write_applied_migrations(session, applied, root_key=root_key)
                session.commit()
            except Exception as exc:
                session.abort()
                raise MigrationError(f"failed to apply migration {step.id}") from exc
    except BaseException as exc:
        operation_error = exc
        raise
    finally:
        if lock is not None:
            try:
                release_migration_lock(session, lock, force=force_lock)
            except Exception:
                if operation_error is None:
                    raise
    return MigrationResult("upgrade", target, tuple(step.id for step in pending))


def downgrade(
    session: gemstone.GemStoneSession,
    steps: Sequence[MigrationInput],
    *,
    target: str | None = None,
    dry_run: bool = False,
    root_key: str = DEFAULT_VERSION_ROOT,
    use_lock: bool = True,
    lock_key: str | None = None,
    lock_owner: str | None = None,
    lock_stale_after_seconds: float | None = DEFAULT_LOCK_STALE_AFTER_SECONDS,
    force_lock: bool = False,
    record_dry_run: bool = False,
) -> MigrationResult:
    """Roll back applied module-style migrations down to ``target``."""
    applied = applied_migrations(session, root_key=root_key)
    ordered = validate_migration_state(steps, applied)
    pending = plan_downgrade(ordered, applied, target=target)
    missing = [step.id for step in pending if step.downgrade is None]
    if missing:
        raise MigrationError(f"migration(s) do not support downgrade: {', '.join(missing)}")
    if dry_run:
        operations = _record_pending_steps(pending, direction="downgrade") if record_dry_run else ()
        return MigrationResult(
            "downgrade",
            target,
            tuple(step.id for step in pending),
            True,
            operations,
        )

    lock = (
        acquire_migration_lock(
            session,
            root_key=root_key,
            lock_key=lock_key,
            owner=lock_owner,
            stale_after_seconds=lock_stale_after_seconds,
            force=force_lock,
        )
        if use_lock and pending
        else None
    )
    operation_error: BaseException | None = None
    try:
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
    except BaseException as exc:
        operation_error = exc
        raise
    finally:
        if lock is not None:
            try:
                release_migration_lock(session, lock, force=force_lock)
            except Exception:
                if operation_error is None:
                    raise
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
    plan_parser = subcommands.add_parser("plan", help="Print pending migration steps.")
    _add_online_arguments(plan_parser)
    plan_parser.add_argument(
        "--direction",
        choices=("upgrade", "downgrade"),
        default="upgrade",
        help="Plan direction.",
    )
    plan_parser.add_argument("--target", help="Migration id target. Use base for full rollback.")

    current_parser = subcommands.add_parser("current", help="Print the current migration id.")
    current_parser.add_argument(
        "--root-key",
        default=DEFAULT_VERSION_ROOT,
        help="UserGlobals key that stores applied migration metadata.",
    )
    status_parser = subcommands.add_parser("status", help="Print applied and pending migrations.")
    _add_online_arguments(status_parser)

    upgrade_parser = subcommands.add_parser("upgrade", help="Apply pending migrations.")
    _add_online_arguments(upgrade_parser)
    _add_lock_arguments(upgrade_parser)
    upgrade_parser.add_argument("--target", help="Stop after applying this migration id.")
    upgrade_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the pending steps without applying them.",
    )
    upgrade_parser.add_argument(
        "--record",
        action="store_true",
        help="With --dry-run, run callbacks against a recording session.",
    )

    downgrade_parser = subcommands.add_parser("downgrade", help="Roll back applied migrations.")
    _add_online_arguments(downgrade_parser)
    _add_lock_arguments(downgrade_parser)
    downgrade_parser.add_argument(
        "--target",
        default="base",
        help="Migration id to keep applied. Defaults to base.",
    )
    downgrade_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the rollback steps without applying them.",
    )
    downgrade_parser.add_argument(
        "--record",
        action="store_true",
        help="With --dry-run, run callbacks against a recording session.",
    )
    diff_parser = subcommands.add_parser(
        "diff-class",
        help="Compare a GemStone class with a local Python type witness.",
    )
    diff_parser.add_argument("class_name", help="GemStone class name to inspect.")
    diff_parser.add_argument(
        "--local-class",
        required=True,
        help="Python class reference as module:qualname.",
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
    if args.command == "current":
        with _session_from_env() as session:
            print(current_version(session, root_key=args.root_key) or "base")
        return 0
    if args.command == "status":
        steps = load_manifest(args.manifest)
        with _session_from_env() as session:
            status = migration_status(session, steps, root_key=args.root_key)
        _print_status(status)
        return 0
    if args.command == "plan":
        steps = load_manifest(args.manifest)
        with _session_from_env() as session:
            applied = applied_migrations(session, root_key=args.root_key)
            ordered = validate_migration_state(steps, applied)
            if args.direction == "upgrade":
                pending = plan_upgrade(ordered, applied, target=args.target)
            else:
                pending = plan_downgrade(ordered, applied, target=args.target)
        _print_steps(args.direction, pending)
        return 0
    if args.command == "upgrade":
        steps = load_manifest(args.manifest)
        with _session_from_env() as session:
            result = upgrade(
                session,
                steps,
                target=args.target,
                dry_run=bool(args.dry_run),
                root_key=args.root_key,
                use_lock=not bool(args.no_lock),
                lock_key=args.lock_key,
                lock_owner=args.lock_owner,
                lock_stale_after_seconds=args.lock_stale_after,
                force_lock=bool(args.force_lock),
                record_dry_run=bool(args.record),
            )
        _print_result(result)
        return 0
    if args.command == "downgrade":
        steps = load_manifest(args.manifest)
        with _session_from_env() as session:
            result = downgrade(
                session,
                steps,
                target=args.target,
                dry_run=bool(args.dry_run),
                root_key=args.root_key,
                use_lock=not bool(args.no_lock),
                lock_key=args.lock_key,
                lock_owner=args.lock_owner,
                lock_stale_after_seconds=args.lock_stale_after,
                force_lock=bool(args.force_lock),
                record_dry_run=bool(args.record),
            )
        _print_result(result)
        return 0
    if args.command == "diff-class":
        local_class = _load_class(args.local_class)
        with _session_from_env() as session:
            class_diff = diff_class(session, args.class_name, local_class=local_class)
        _print_class_diff(class_diff)
        return 0
    parser.error(f"unknown command {args.command!r}")
    return 2


def main_entry() -> None:
    """Console-script wrapper for ``gemstone-migrations``."""
    raise SystemExit(main())


def _add_online_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--manifest",
        required=True,
        help="Python module containing migrations or MIGRATIONS.",
    )
    parser.add_argument(
        "--root-key",
        default=DEFAULT_VERSION_ROOT,
        help="UserGlobals key that stores applied migration metadata.",
    )


def _add_lock_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--no-lock",
        action="store_true",
        help="Do not acquire the GemStone-side advisory migration lock.",
    )
    parser.add_argument("--lock-key", help="Override the UserGlobals migration lock key.")
    parser.add_argument("--lock-owner", help="Override the lock owner string.")
    parser.add_argument(
        "--lock-stale-after",
        type=float,
        default=float(DEFAULT_LOCK_STALE_AFTER_SECONDS),
        help="Seconds after which an existing lock is considered stale.",
    )
    parser.add_argument(
        "--force-lock",
        action="store_true",
        help="Replace an existing lock even when it is not stale.",
    )


def _session_from_env() -> gemstone.GemStoneSession:
    return gemstone.GemStoneSession(config=gemstone.GemStoneConfig.from_env())


def _print_steps(direction: str, steps: Sequence[MigrationStep]) -> None:
    print(f"{direction}: {len(steps)} step(s)")
    for step in steps:
        suffix = f" - {step.description}" if step.description else ""
        print(f"  {step.id}{suffix}")


def _print_result(result: MigrationResult) -> None:
    label = f"{result.direction} dry-run" if result.dry_run else result.direction
    print(f"{label}: {len(result.steps)} step(s)")
    for migration_id in result.steps:
        print(f"  {migration_id}")
    if result.operations:
        print("recorded operations:")
        for operation in result.operations:
            print(f"  {operation}")


def _print_status(status: MigrationStatus) -> None:
    print(f"current: {status.current or 'base'}")
    print(f"applied: {len(status.applied)}")
    for migration_id in status.applied:
        print(f"  {migration_id}")
    print(f"pending: {len(status.pending)}")
    for migration_id in status.pending:
        print(f"  {migration_id}")


def _print_class_diff(class_diff: ClassDiff) -> None:
    print(f"class: {class_diff.class_name}")
    print(f"local: {class_diff.local_class_name}")
    print(f"remote instvars: {', '.join(class_diff.remote_instvars) or '(none)'}")
    print(f"local instvars: {', '.join(class_diff.local_instvars) or '(none)'}")
    print(f"missing instvars: {', '.join(class_diff.missing_instvars) or '(none)'}")
    print(f"extra instvars: {', '.join(class_diff.extra_instvars) or '(none)'}")
    if class_diff.suggested_upgrade:
        print("suggested upgrade:")
        for line in class_diff.suggested_upgrade:
            print(f"  {line}")
    if class_diff.suggested_downgrade:
        print("suggested downgrade:")
        for line in class_diff.suggested_downgrade:
            print(f"  {line}")


def _coerce_steps(entries: Iterable[MigrationInput]) -> tuple[MigrationStep, ...]:
    steps: list[MigrationStep] = []
    for entry in entries:
        if isinstance(entry, MigrationStep):
            steps.append(entry)
        else:
            steps.append(migration_from_module(entry))
    return tuple(steps)


def _record_pending_steps(
    pending: Sequence[MigrationStep],
    *,
    direction: str,
) -> tuple[str, ...]:
    recorder = RecordingMigrationSession()
    for step in pending:
        recorder.operations.append(f"# {direction} {step.id}")
        callback = step.upgrade if direction == "upgrade" else step.downgrade
        if callback is None:
            raise MigrationError(f"migration {step.id} does not support {direction}")
        callback(recorder)
    return tuple(recorder.operations)


def _load_class(spec: str) -> type[Any]:
    if ":" not in spec:
        raise MigrationError("--local-class must be formatted as module:ClassName")
    module_name, qualname = spec.split(":", 1)
    obj: object = importlib.import_module(module_name)
    for part in qualname.split("."):
        obj = getattr(obj, part)
    if not isinstance(obj, type):
        raise MigrationError(f"{spec!r} does not refer to a Python class")
    return obj


def _local_instvars(local_class: type[Any]) -> tuple[str, ...]:
    names: list[str] = []
    annotations = getattr(local_class, "__annotations__", {})
    if isinstance(annotations, Mapping):
        for name in annotations:
            if not name.startswith("_"):
                names.append(str(name))
    for name, member in local_class.__dict__.items():
        if not name.startswith("_") and isinstance(member, property):
            names.append(name)
    return tuple(dict.fromkeys(names))


def _class_instvar_source(class_name: str, instvar_name: str, *, add: bool) -> str:
    selector = "addInstVarName:" if add else "removeInstVarName:"
    return f"{class_name} {selector} '{_escape_smalltalk_string(instvar_name)}'"


def _escape_smalltalk_string(value: str) -> str:
    return value.replace("'", "''")


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


def _check_applied_against_manifest(
    ordered: Sequence[MigrationStep],
    applied: Iterable[str] | Mapping[str, object],
) -> None:
    by_id = {step.id: step for step in ordered}
    applied_ids = _applied_id_set(applied)
    unknown = sorted(applied_ids - set(by_id))
    if unknown:
        raise MigrationError(
            "GemStone has applied migration(s) not present in the local manifest: "
            + ", ".join(unknown)
        )
    if not isinstance(applied, Mapping):
        return
    for migration_id, raw_record in applied.items():
        record = raw_record if isinstance(raw_record, Mapping) else {}
        stored_checksum = str(record.get("checksum", ""))
        local_checksum = by_id[str(migration_id)].checksum
        if stored_checksum and local_checksum and stored_checksum != local_checksum:
            raise MigrationError(
                f"checksum mismatch for applied migration {migration_id}: "
                f"GemStone has {stored_checksum}, local file has {local_checksum}"
            )


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


def _normalize_lock(record: object) -> dict[str, str]:
    if record is None:
        return {}
    if not hasattr(record, "items"):
        return {"owner": str(record), "acquired_at": "", "root_key": DEFAULT_VERSION_ROOT}
    return {str(key): str(value) for key, value in record.items()}


def _lock_is_stale(
    record: Mapping[str, str],
    stale_after_seconds: float | None,
) -> bool:
    if stale_after_seconds is None:
        return False
    acquired_at = record.get("acquired_at", "")
    if not acquired_at:
        return False
    try:
        acquired = datetime.fromisoformat(acquired_at)
    except ValueError:
        return False
    if acquired.tzinfo is None:
        acquired = acquired.replace(tzinfo=timezone.utc)
    elapsed = datetime.now(timezone.utc) - acquired.astimezone(timezone.utc)
    return elapsed.total_seconds() > stale_after_seconds


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_lock_owner() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def _current_version_from_applied(applied: Mapping[str, Mapping[str, str]]) -> str | None:
    if not applied:
        return None
    latest = max(
        applied.values(),
        key=lambda record: (record.get("applied_at", ""), record.get("id", "")),
    )
    return latest.get("id")


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
