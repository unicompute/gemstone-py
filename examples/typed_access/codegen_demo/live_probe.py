"""Probe the generated Codegen wrapper against a live GemStone stone.

Run from the repository root after setting the usual GemStone environment:

    export GS_USERNAME=DataCurator
    export GS_PASSWORD=swordfish
    export GS_STONE_NAME=gs64stone
    python -m examples.typed_access.codegen_demo.live_probe --booking-id B-1001

The example intentionally keeps the Smalltalk surface in generated wrappers:
application code imports `OkzBooking` and calls Python methods.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from gemstone_py import GemStoneConfig, GemStoneConfigurationError, GemStoneSession

from .generated import OkzBooking


def build_parser() -> argparse.ArgumentParser:
    """Build the live probe parser."""
    parser = argparse.ArgumentParser(
        prog="python -m examples.typed_access.codegen_demo.live_probe",
        description="Call generated wrappers against a configured GemStone stone.",
    )
    parser.add_argument(
        "--booking-id",
        default="B-1001",
        help="Booking id passed to OkzBooking findById:.",
    )
    parser.add_argument(
        "--mark-paid-at",
        type=int,
        default=0,
        help="Optional POSIX timestamp passed to markPaid:. Omit or set 0 to skip.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the live generated-wrapper probe."""
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        config = GemStoneConfig.from_env()
    except GemStoneConfigurationError as exc:
        print(f"Missing GemStone configuration: {exc}")
        print("")
        print("Set the live environment first, for example:")
        print("  export GS_STONE_NAME=gs64stone")
        print("  export GS_USERNAME=DataCurator")
        print("  export GS_PASSWORD=swordfish")
        return 2

    with GemStoneSession(config=config) as session:
        booking = OkzBooking.find_by_id(session, args.booking_id)
        print(f"GemStone class: {booking.gemstone_class_name}")
        print(f"Booking id:     {args.booking_id}")
        print(f"Status:         {booking.status}")

        customer = booking.customer()
        print(f"Customer class: {customer.gemstone_class_name}")
        print(f"Customer name:  {customer.name}")

        if args.mark_paid_at:
            booking.mark_paid(args.mark_paid_at)
            print(f"markPaid: sent with {args.mark_paid_at}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
