"""GemStone-side bootstrap helpers for gemstone-py conventions."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from importlib.resources import files

from gemstone_py.client import (
    GemStoneConfig,
    GemStoneConfigurationError,
    GemStoneSession,
    TransactionPolicy,
)

BOOTSTRAP_VERSION = "1"
BOOTSTRAP_MARKER_KEY = "GemstonePyBootstrapVersion"


@dataclass(frozen=True)
class BootstrapArtifact:
    """A GemStone-side convention used by gemstone-py."""

    name: str
    description: str
    expected_class: str
    user_globals_key: str | None
    status_expression: str | None = None


@dataclass(frozen=True)
class BootstrapArtifactStatus:
    """Presence check result for one GemStone-side artifact."""

    artifact: BootstrapArtifact
    present: bool


@dataclass(frozen=True)
class BootstrapResult:
    """Result from applying the packaged GemStone-side bootstrap script."""

    version: str
    applied: bool
    message: str
    created_keys: tuple[str, ...]
    before: tuple[BootstrapArtifactStatus, ...]
    after: tuple[BootstrapArtifactStatus, ...]
    source: str


BOOTSTRAP_ARTIFACTS: tuple[BootstrapArtifact, ...] = (
    BootstrapArtifact(
        name=BOOTSTRAP_MARKER_KEY,
        description="Version marker written by the gemstone-py bootstrap script.",
        expected_class="String",
        user_globals_key=BOOTSTRAP_MARKER_KEY,
    ),
    BootstrapArtifact(
        name="GStoreRoot",
        description="Root dictionary for GStore named key/value stores.",
        expected_class="StringKeyValueDictionary",
        user_globals_key="GStoreRoot",
    ),
    BootstrapArtifact(
        name="GSQueryRoot",
        description="Root dictionary for GSCollection named IdentitySets.",
        expected_class="Dictionary",
        user_globals_key="GSQueryRoot",
    ),
    BootstrapArtifact(
        name="ObjectLogEntry objectLog",
        description="GemStone built-in object log used by gemstone_py.objectlog.",
        expected_class="ObjectLog",
        user_globals_key=None,
        status_expression="ObjectLogEntry objectLog notNil",
    ),
)


def bootstrap_source() -> str:
    """Return the packaged Smalltalk bootstrap source."""
    return (
        files("gemstone_py._gemstone_side")
        .joinpath("init.st")
        .read_text(encoding="utf-8")
    )


def audit(session: GemStoneSession) -> tuple[BootstrapArtifactStatus, ...]:
    """Inspect whether the current GemStone image has gemstone-py artifacts."""
    return tuple(
        BootstrapArtifactStatus(artifact=artifact, present=_artifact_present(session, artifact))
        for artifact in BOOTSTRAP_ARTIFACTS
    )


def bootstrap(session: GemStoneSession, *, dry_run: bool = False) -> BootstrapResult:
    """
    Apply the packaged GemStone-side bootstrap script.

    The script is idempotent: it creates missing gemstone-py helper roots,
    refreshes the bootstrap version marker, and never replaces application data.
    """
    source = bootstrap_source()
    before = audit(session)
    if dry_run:
        return BootstrapResult(
            version=BOOTSTRAP_VERSION,
            applied=False,
            message="dry run: bootstrap source was not evaluated",
            created_keys=(),
            before=before,
            after=before,
            source=source,
        )

    raw_message = session.eval(source)
    after = audit(session)
    created_keys = _created_user_globals_keys(before, after)
    return BootstrapResult(
        version=BOOTSTRAP_VERSION,
        applied=bool(created_keys),
        message=str(raw_message),
        created_keys=created_keys,
        before=before,
        after=after,
        source=source,
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the `gemstone-bootstrap` command-line parser."""
    parser = argparse.ArgumentParser(
        prog="gemstone-bootstrap",
        description="Audit or initialize GemStone-side gemstone-py conventions.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Connect to GemStone and report bootstrap artifact status without changing data.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the bootstrap plan and packaged Smalltalk source without connecting.",
    )
    parser.add_argument(
        "--print-source",
        action="store_true",
        help="Print the packaged Smalltalk bootstrap source.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the GemStone-side bootstrap CLI."""
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.print_source:
        print(bootstrap_source(), end="")
        return 0

    if args.dry_run:
        print("gemstone-py GemStone-side bootstrap dry run")
        print()
        print(_format_artifact_plan())
        print()
        print(bootstrap_source(), end="")
        return 0

    try:
        config = GemStoneConfig.from_env(require_credentials=True)
        policy = (
            TransactionPolicy.ABORT_ON_EXIT
            if args.status
            else TransactionPolicy.COMMIT_ON_SUCCESS
        )
        with GemStoneSession(config=config, transaction_policy=policy) as session:
            if args.status:
                print(_format_statuses(audit(session)))
                return 0
            result = bootstrap(session)
    except GemStoneConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(result.message)
    if result.created_keys:
        print("Created UserGlobals keys: " + ", ".join(result.created_keys))
    else:
        print("No UserGlobals keys were missing.")
    print()
    print(_format_statuses(result.after))
    return 0


def main_entry() -> None:
    """Console-script wrapper for `gemstone-bootstrap`."""
    raise SystemExit(main())


def _format_artifact_plan() -> str:
    lines = ["Artifacts:"]
    for artifact in BOOTSTRAP_ARTIFACTS:
        location = (
            f"UserGlobals at: #{artifact.user_globals_key}"
            if artifact.user_globals_key is not None
            else artifact.name
        )
        lines.append(
            f"  - {location} ({artifact.expected_class}): {artifact.description}"
        )
    return "\n".join(lines)


def _format_statuses(statuses: Sequence[BootstrapArtifactStatus]) -> str:
    lines = ["GemStone-side gemstone-py artifact status:"]
    for status in statuses:
        artifact = status.artifact
        state = "present" if status.present else "missing"
        location = (
            f"UserGlobals at: #{artifact.user_globals_key}"
            if artifact.user_globals_key is not None
            else artifact.name
        )
        lines.append(f"  - {state}: {location} ({artifact.expected_class})")
    return "\n".join(lines)


def _artifact_present(session: GemStoneSession, artifact: BootstrapArtifact) -> bool:
    if artifact.user_globals_key is not None:
        return bool(session.eval(_user_globals_contains_source(artifact.user_globals_key)))
    expression = artifact.status_expression
    if expression is None:
        return False
    return bool(session.eval(expression))


def _created_user_globals_keys(
    before: Sequence[BootstrapArtifactStatus],
    after: Sequence[BootstrapArtifactStatus],
) -> tuple[str, ...]:
    before_by_name = {status.artifact.name: status for status in before}
    created: list[str] = []
    for status in after:
        key = status.artifact.user_globals_key
        if key is None or not status.present:
            continue
        previous = before_by_name.get(status.artifact.name)
        if previous is not None and not previous.present:
            created.append(key)
    return tuple(created)


def _user_globals_contains_source(key: str) -> str:
    return f"UserGlobals includesKey: {_smalltalk_symbol(key)}"


def _smalltalk_symbol(name: str) -> str:
    if not name or not name.isalnum():
        raise ValueError(f"Cannot render {name!r} as a Smalltalk symbol literal")
    return f"#{name}"


__all__ = [
    "BOOTSTRAP_ARTIFACTS",
    "BOOTSTRAP_MARKER_KEY",
    "BOOTSTRAP_VERSION",
    "BootstrapArtifact",
    "BootstrapArtifactStatus",
    "BootstrapResult",
    "audit",
    "bootstrap",
    "bootstrap_source",
    "build_parser",
    "main",
    "main_entry",
]


if __name__ == "__main__":
    main_entry()
