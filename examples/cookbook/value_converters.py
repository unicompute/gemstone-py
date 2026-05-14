"""Preview explicit value converters without requiring a live GemStone stone.

Run from the repository root:

    python -m examples.cookbook.value_converters

This example keeps conversion explicit: application code decides which Python
values should be adapted before passing OOP markers into gemstone-py calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from gemstone_py import dataclass_to_dict, scalar_value_converter_registry


class PreviewSession:
    """Tiny session-shaped object used only for this offline example."""

    def __init__(self) -> None:
        self._next_oop = 4100
        self.created_strings: list[str] = []
        self.evaluated_sources: list[str] = []

    def _allocate_oop(self) -> int:
        self._next_oop += 1
        return self._next_oop

    def new_string(self, value: str) -> int:
        self.created_strings.append(value)
        return self._allocate_oop()

    def eval_oop(self, source: str) -> int:
        self.evaluated_sources.append(source)
        return self._allocate_oop()


@dataclass(frozen=True)
class BookingPatch:
    booking_id: str
    due_on: date
    total: Decimal


def main() -> int:
    """Print the offline converter preview."""
    session = PreviewSession()
    registry = scalar_value_converter_registry()

    values = [
        datetime(2026, 5, 14, 12, 30, tzinfo=timezone.utc),
        date(2026, 5, 15),
        Decimal("19.95"),
        UUID("12345678-1234-5678-1234-567812345678"),
    ]
    oop_markers = registry.to_oops(session, values)

    patch = BookingPatch("B-1001", date(2026, 5, 15), Decimal("19.95"))
    payload = dataclass_to_dict(patch, recurse=False)

    print("gemstone-py lightweight value converter preview")
    print(f"  Registered converters: {', '.join(registry.names())}")
    print(f"  Converted OOP markers: {[marker.oop for marker in oop_markers]}")
    print(f"  GemStone strings created: {session.created_strings}")
    print(f"  GemStone expressions evaluated: {len(session.evaluated_sources)}")
    print(f"  Plain payload: {payload}")
    print("")
    print("Use the OOP markers explicitly with perform calls, root updates, or proxy APIs.")
    print("Keep domain objects in application code unless a real app proves it needs mapping.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
