"""Shared Smalltalk snippet helpers for batched GemStone fetches."""

from __future__ import annotations

from typing import Any, Protocol

__all__ = [
    "decode_escaped_field",
    "fetch_collection_oops",
    "fetch_mapping_string_oop_lists",
    "escaped_field_encoder_source",
    "fetch_mapping_string_keys",
    "fetch_mapping_oop_pairs",
    "fetch_mapping_string_oop_pairs",
    "fetch_mapping_string_pairs",
    "json_string_encoder_source",
    "object_for_oop_expr",
    "parse_escaped_lines",
    "parse_escaped_pairs",
]


class SupportsEval(Protocol):
    """Minimal session protocol for the shared batch helpers."""

    def eval(self, source: str) -> Any:
        ...


def object_for_oop_expr(oop: int) -> str:
    """Return the plain-GemStone object lookup expression for an OOP."""
    return f"Object _objectForOop: {oop}"


def escaped_field_encoder_source(var_name: str = "encode") -> str:
    """Return a Smalltalk block that escapes backslash/newline/pipe fields."""
    return (
        f"{var_name} := [:value | | text |\n"
        "  text := value isNil ifTrue: [''] ifFalse: [value asString].\n"
        "  text := text copyReplaceAll: '\\' with: '\\\\'.\n"
        "  text := text copyReplaceAll: String cr with: '\\r'.\n"
        "  text := text copyReplaceAll: String lf with: '\\n'.\n"
        "  text := text copyReplaceAll: '|' with: '\\p'.\n"
        "  text\n"
        "].\n"
    )


def json_string_encoder_source(var_name: str = "encodeString") -> str:
    """Return a Smalltalk block that JSON-escapes string content."""
    return (
        f"{var_name} := [:text | | escaped |\n"
        "  escaped := text asString.\n"
        "  escaped := escaped copyReplaceAll: '\\' with: '\\\\'.\n"
        "  escaped := escaped copyReplaceAll: '\"' with: '\\\"'.\n"
        "  escaped := escaped copyReplaceAll: String cr with: '\\r'.\n"
        "  escaped := escaped copyReplaceAll: String lf with: '\\n'.\n"
        "  escaped\n"
        "].\n"
    )


def decode_escaped_field(value: str) -> str:
    """Decode a field escaped by our Smalltalk-side batch serializers."""
    if "\\" not in value:
        return value

    decoded: list[str] = []
    i = 0
    while i < len(value):
        ch = value[i]
        if ch != "\\":
            decoded.append(ch)
            i += 1
            continue

        i += 1
        if i >= len(value):
            decoded.append("\\")
            break

        escaped = value[i]
        if escaped == "n":
            decoded.append("\n")
        elif escaped == "r":
            decoded.append("\r")
        elif escaped == "p":
            decoded.append("|")
        elif escaped == "\\":
            decoded.append("\\")
        else:
            decoded.append("\\")
            decoded.append(escaped)
        i += 1
    return "".join(decoded)


def parse_escaped_lines(raw: str | None) -> list[str]:
    """Split newline-delimited escaped rows into decoded strings."""
    if not raw:
        return []
    return [decode_escaped_field(line) for line in raw.splitlines() if line]


def parse_escaped_pairs(raw: str | None) -> list[tuple[str, str]]:
    """Split newline-delimited `key|value` rows into decoded pairs."""
    if not raw:
        return []

    pairs: list[tuple[str, str]] = []
    for line in raw.splitlines():
        if not line:
            continue
        key, sep, value = line.partition("|")
        if not sep:
            continue
        pairs.append((decode_escaped_field(key), decode_escaped_field(value)))
    return pairs


def fetch_mapping_string_keys(
    session: SupportsEval,
    oop: int,
    *,
    iterate_header: str = "mapping associationsDo: [:assoc |",
    key_expr: str = "assoc key asString",
) -> list[str]:
    """Fetch mapping keys in one eval and decode them in Python."""
    raw = session.eval(
        f"| mapping encode stream |\n"
        f"mapping := {object_for_oop_expr(oop)}.\n"
        f"{escaped_field_encoder_source('encode')}"
        "stream := ''.\n"
        f"{iterate_header}\n"
        f"  stream := stream, (encode value: ({key_expr})), String lf asString\n"
        "].\n"
        "stream"
    )
    return parse_escaped_lines(raw)


def fetch_mapping_string_pairs(
    session: SupportsEval,
    oop: int,
    *,
    iterate_header: str = "mapping associationsDo: [:assoc |",
    key_expr: str = "assoc key asString",
    value_expr: str = "assoc value asString",
) -> list[tuple[str, str]]:
    """Fetch mapping key/value string pairs in one eval and decode them."""
    raw = session.eval(
        f"| mapping encode stream |\n"
        f"mapping := {object_for_oop_expr(oop)}.\n"
        f"{escaped_field_encoder_source('encode')}"
        "stream := ''.\n"
        f"{iterate_header}\n"
        "  stream := stream,\n"
        f"    (encode value: ({key_expr})), '|',\n"
        f"    (encode value: ({value_expr})), String lf asString\n"
        "].\n"
        "stream"
    )
    return parse_escaped_pairs(raw)


def fetch_mapping_string_oop_pairs(
    session: SupportsEval,
    oop: int,
    *,
    iterate_header: str = "mapping associationsDo: [:assoc |",
    key_expr: str = "assoc key asString",
    value_expr: str = "assoc value asOop asString",
) -> list[tuple[str, int]]:
    """Fetch mapping key/value pairs where the value is returned as an OOP."""
    pairs = fetch_mapping_string_pairs(
        session,
        oop,
        iterate_header=iterate_header,
        key_expr=key_expr,
        value_expr=value_expr,
    )
    return [(key, int(raw_oop)) for key, raw_oop in pairs]


def fetch_mapping_oop_pairs(
    session: SupportsEval,
    oop: int,
    *,
    iterate_header: str = "mapping associationsDo: [:assoc |",
    key_expr: str = "assoc key asOop asString",
    value_expr: str = "assoc value asOop asString",
) -> list[tuple[int, int]]:
    """Fetch mapping key/value OOP pairs in one eval."""
    pairs = fetch_mapping_string_pairs(
        session,
        oop,
        iterate_header=iterate_header,
        key_expr=key_expr,
        value_expr=value_expr,
    )
    return [(int(raw_key), int(raw_value)) for raw_key, raw_value in pairs]


def fetch_collection_oops(
    session: SupportsEval,
    oop: int,
    *,
    iterate_header: str = "collection do: [:each |",
    value_expr: str = "each asOop asString",
) -> list[int]:
    """Fetch all collection members as raw OOPs in one eval."""
    raw = session.eval(
        f"| collection stream |\n"
        f"collection := {object_for_oop_expr(oop)}.\n"
        "stream := ''.\n"
        f"{iterate_header}\n"
        f"  stream := stream, ({value_expr}), String lf asString\n"
        "].\n"
        "stream"
    )
    return [int(raw_oop) for raw_oop in parse_escaped_lines(raw)]


def fetch_mapping_string_oop_lists(
    session: SupportsEval,
    oop: int,
    *,
    iterate_header: str = "mapping associationsDo: [:assoc |",
    key_expr: str = "assoc key asString",
    value_collection_expr: str = "assoc value",
) -> list[tuple[str, list[int]]]:
    """Fetch string-keyed collections as `[(key, [oop, ...]), ...]` in one eval."""
    raw = session.eval(
        f"| mapping encode stream |\n"
        f"mapping := {object_for_oop_expr(oop)}.\n"
        f"{escaped_field_encoder_source('encode')}"
        "stream := ''.\n"
        f"{iterate_header}\n"
        "  stream := stream, (encode value: ("
        f"{key_expr}"
        ")).\n"
        f"  ({value_collection_expr}) do: [:value |\n"
        "    stream := stream, '|', value asOop asString\n"
        "  ].\n"
        "  stream := stream, String lf asString\n"
        "].\n"
        "stream"
    )
    if not raw:
        return []

    rows: list[tuple[str, list[int]]] = []
    for line in raw.splitlines():
        if not line:
            continue
        fields = line.split("|")
        key = decode_escaped_field(fields[0])
        values = [int(field) for field in fields[1:] if field]
        rows.append((key, values))
    return rows
