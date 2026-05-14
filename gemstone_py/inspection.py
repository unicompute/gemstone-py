"""Inspect and describe GemStone objects from Python."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any, Sequence

from gemstone_py._smalltalk_batch import (
    decode_escaped_field,
    escaped_field_encoder_source,
    object_for_oop_expr,
)
from gemstone_py.client import GemStoneConfig, GemStoneSession


@dataclass(frozen=True)
class InspectedReference:
    """One referenced GemStone object value."""

    oop: int
    class_name: str
    summary: str

    def __repr__(self) -> str:
        return f"<GemStone {self.class_name} oop=0x{self.oop:X} {self.summary!r}>"


@dataclass(frozen=True)
class InspectedSlot:
    """One named instance variable from an inspected object."""

    name: str
    value: InspectedReference


@dataclass(frozen=True)
class InspectionResult:
    """One-level inspection result for a GemStone object."""

    oop: int
    class_name: str
    summary: str
    slots: list[InspectedSlot]


@dataclass(frozen=True)
class ClassDescription:
    """Description of a GemStone class."""

    name: str
    superclasses: list[str]
    instvars: list[str]
    class_instvars: list[str]
    instance_count: int | None


def inspect_oop(
    session: GemStoneSession,
    oop: int,
    *,
    slots: Sequence[str] | None = None,
) -> InspectionResult:
    """Return a one-level inspection of ``oop``."""
    slot_filter = _name_filter(slots)
    rows = _rows(session.eval(_inspect_source(oop)))
    if not rows:
        raise RuntimeError(f"GemStone inspection returned no rows for OOP {oop}")

    header = rows[0]
    class_name = header[0] if len(header) > 0 else "Object"
    summary = header[1] if len(header) > 1 else ""
    inspected_slots: list[InspectedSlot] = []
    for row in rows[1:]:
        if len(row) < 4:
            continue
        name, raw_oop, slot_class, slot_summary = row[:4]
        if slot_filter is not None and name not in slot_filter:
            continue
        try:
            slot_oop = int(raw_oop)
        except ValueError:
            continue
        inspected_slots.append(
            InspectedSlot(
                name=name,
                value=InspectedReference(
                    oop=slot_oop,
                    class_name=slot_class,
                    summary=slot_summary,
                ),
            )
        )
    return InspectionResult(
        oop=int(oop),
        class_name=class_name,
        summary=summary,
        slots=inspected_slots,
    )


def dump_oop(
    session: GemStoneSession,
    oop: int,
    *,
    depth: int = 2,
    slots: Sequence[str] | None = None,
    classes: Sequence[str] | None = None,
    _seen: set[int] | None = None,
) -> dict[str, Any]:
    """Return a recursive, JSON-serialisable structure dump for ``oop``."""
    if depth < 0:
        raise ValueError("depth must be at least 0")
    class_filter = _name_filter(classes)
    seen = set(_seen or set())
    ref_oop = int(oop)
    if ref_oop in seen:
        return {"oop": ref_oop, "cycle": True}
    seen.add(ref_oop)

    inspected = inspect_oop(session, ref_oop, slots=slots)
    payload: dict[str, Any] = {
        "oop": inspected.oop,
        "class_name": inspected.class_name,
        "summary": inspected.summary,
    }
    if class_filter is not None and inspected.class_name not in class_filter:
        payload["filtered"] = True
        return payload
    if depth == 0:
        return payload

    slot_payload: dict[str, Any] = {}
    for slot in inspected.slots:
        value = slot.value
        if depth <= 1:
            slot_payload[slot.name] = asdict(value)
        else:
            slot_payload[slot.name] = dump_oop(
                session,
                value.oop,
                depth=depth - 1,
                slots=slots,
                classes=classes,
                _seen=seen,
            )
    payload["slots"] = slot_payload
    return payload


def format_inspection(result: InspectionResult) -> str:
    """Return a compact terminal rendering of a one-level inspection."""
    lines = [f"{result.class_name}  oop=0x{result.oop:X}", f"  {result.summary}"]
    for slot in result.slots:
        lines.append(
            f"  {slot.name}: {slot.value.class_name} "
            f"oop=0x{slot.value.oop:X} {slot.value.summary}"
        )
    return "\n".join(lines)


def format_dump(payload: Mapping[str, Any]) -> str:
    """Return a compact terminal rendering of ``dump_oop`` output."""
    lines: list[str] = []
    _format_dump_into(payload, lines, indent=0, slot_name=None)
    return "\n".join(lines)


def describe_class(session: GemStoneSession, name: str) -> ClassDescription:
    """Return superclass and instance-variable details for a GemStone class."""
    class_oop = session.resolve(name)
    rows = _rows(session.eval(_describe_class_source(class_oop)))
    if not rows:
        raise RuntimeError(f"GemStone class description returned no rows for {name!r}")

    header = rows[0]
    resolved_name = header[0] if len(header) > 0 else name
    raw_count = header[1] if len(header) > 1 else ""
    instance_count = int(raw_count) if raw_count.isdigit() else None
    superclasses: list[str] = []
    instvars: list[str] = []
    class_instvars: list[str] = []
    for row in rows[1:]:
        if len(row) < 2:
            continue
        kind, value = row[0], row[1]
        if kind == "superclass":
            superclasses.append(value)
        elif kind == "instvar":
            instvars.append(value)
        elif kind == "class_instvar":
            class_instvars.append(value)

    return ClassDescription(
        name=resolved_name,
        superclasses=superclasses,
        instvars=instvars,
        class_instvars=class_instvars,
        instance_count=instance_count,
    )


def _rows(raw: Any) -> list[list[str]]:
    if raw is None:
        return []
    rows: list[list[str]] = []
    for line in str(raw).splitlines():
        if not line:
            continue
        rows.append([decode_escaped_field(part) for part in line.split("|")])
    return rows


def _name_filter(names: Sequence[str] | None) -> set[str] | None:
    if names is None:
        return None
    return {name for name in names if name}


def _format_dump_into(
    payload: Mapping[str, Any],
    lines: list[str],
    *,
    indent: int,
    slot_name: str | None,
) -> None:
    prefix = "  " * indent
    label = f"{slot_name}: " if slot_name else ""
    oop = payload.get("oop", "?")
    if payload.get("cycle"):
        lines.append(f"{prefix}{label}<cycle oop={_format_oop(oop)}>")
        return

    class_name = payload.get("class_name", "Object")
    summary = str(payload.get("summary", ""))
    filtered = " [filtered]" if payload.get("filtered") else ""
    suffix = f" {summary}" if summary else ""
    lines.append(f"{prefix}{label}{class_name} oop={_format_oop(oop)}{filtered}{suffix}")

    slots = payload.get("slots")
    if not isinstance(slots, Mapping):
        return
    for child_name, child in slots.items():
        if isinstance(child, Mapping):
            _format_dump_into(
                child,
                lines,
                indent=indent + 1,
                slot_name=str(child_name),
            )
        else:
            lines.append(f"{prefix}  {child_name}: {child!r}")


def _format_oop(oop: Any) -> str:
    try:
        return f"0x{int(oop):X}"
    except (TypeError, ValueError):
        return str(oop)


def _inspect_source(oop: int) -> str:
    obj_expr = object_for_oop_expr(int(oop))
    return (
        "| obj cls names stream encode safePrint |\n"
        f"obj := {obj_expr}.\n"
        "cls := obj class.\n"
        f"{escaped_field_encoder_source('encode')}"
        "safePrint := [:value | [value printString] on: Error do: [:ex | '<print failed>']].\n"
        "stream := (encode value: cls name asString), '|', "
        "(encode value: (safePrint value: obj)), String lf asString.\n"
        "names := [cls allInstVarNames] on: Error do: [:ex | #()].\n"
        "1 to: names size do: [:index | | value |\n"
        "  value := [obj instVarAt: index] on: Error do: [:ex | nil].\n"
        "  stream := stream,\n"
        "    (encode value: ((names at: index) asString)), '|',\n"
        "    value asOop asString, '|',\n"
        "    (encode value: value class name asString), '|',\n"
        "    (encode value: (safePrint value: value)), String lf asString\n"
        "].\n"
        "stream"
    )


def _describe_class_source(class_oop: int) -> str:
    cls_expr = object_for_oop_expr(int(class_oop))
    return (
        "| cls current stream encode instNames classInstNames instanceCount |\n"
        f"cls := {cls_expr}.\n"
        f"{escaped_field_encoder_source('encode')}"
        "instanceCount := [(cls allInstances size) asString] on: Error do: [:ex | ''].\n"
        "stream := (encode value: cls name asString), '|', instanceCount, String lf asString.\n"
        "current := cls superclass.\n"
        "[current notNil] whileTrue: [\n"
        "  stream := stream, 'superclass|', (encode value: current name asString), "
        "String lf asString.\n"
        "  current := current superclass\n"
        "].\n"
        "instNames := [cls allInstVarNames] on: Error do: [:ex | #()].\n"
        "instNames do: [:name |\n"
        "  stream := stream, 'instvar|', (encode value: name asString), String lf asString\n"
        "].\n"
        "classInstNames := [cls class allInstVarNames] on: Error do: [:ex | #()].\n"
        "classInstNames do: [:name |\n"
        "  stream := stream, 'class_instvar|', (encode value: name asString), String lf asString\n"
        "].\n"
        "stream"
    )


def _print_inspection(result: InspectionResult) -> None:
    print(format_inspection(result))


def _print_class_description(description: ClassDescription) -> None:
    print(description.name)
    if description.instance_count is not None:
        print(f"  instances: {description.instance_count}")
    if description.superclasses:
        print(f"  superclasses: {' < '.join(description.superclasses)}")
    if description.instvars:
        print("  instance variables:")
        for name in description.instvars:
            print(f"    {name}")
    if description.class_instvars:
        print("  class instance variables:")
        for name in description.class_instvars:
            print(f"    {name}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gemstone-inspect",
        description="Inspect GemStone objects and classes from Python.",
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--oop", type=int, help="Raw GemStone OOP to inspect.")
    target.add_argument("--class", dest="class_name", help="GemStone class name to describe.")
    parser.add_argument("--dump", action="store_true", help="Recursively dump an OOP.")
    parser.add_argument("--depth", type=int, default=2, help="Recursive dump depth.")
    parser.add_argument(
        "--slot",
        dest="slots",
        action="append",
        help="Only include this slot name.",
    )
    parser.add_argument(
        "--include-class",
        dest="classes",
        action="append",
        help="Only recurse through this GemStone class name.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    with GemStoneSession(config=GemStoneConfig.from_env()) as session:
        if args.class_name:
            description = describe_class(session, args.class_name)
            if args.json:
                print(json.dumps(asdict(description), indent=2, sort_keys=True))
            else:
                _print_class_description(description)
            return 0

        if args.dump:
            payload = dump_oop(
                session,
                args.oop,
                depth=args.depth,
                slots=args.slots,
                classes=args.classes,
            )
            if args.json:
                print(json.dumps(payload, indent=2, sort_keys=True))
            else:
                print(format_dump(payload))
            return 0

        result = inspect_oop(session, args.oop, slots=args.slots)
        if args.json:
            print(json.dumps(asdict(result), indent=2, sort_keys=True))
        else:
            _print_inspection(result)
        return 0


def main_entry() -> None:
    raise SystemExit(main())


__all__ = [
    "ClassDescription",
    "format_dump",
    "format_inspection",
    "InspectedReference",
    "InspectedSlot",
    "InspectionResult",
    "build_parser",
    "describe_class",
    "dump_oop",
    "inspect_oop",
    "main",
    "main_entry",
]
