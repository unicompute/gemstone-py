"""Installed CLI entry points for gemstone-py demos."""

from __future__ import annotations

import argparse
import platform
import sys
from collections.abc import Sequence

from gemstone_py.example_support import MANUAL_POLICY, example_session
from gemstone_py.session_facade import GemStoneSessionFacade
from gemstone_py.smalltalk_bridge import SmalltalkBridge


def run_hello() -> None:
    """Print local Python runtime information."""
    print("Hello from:")
    print(f"  Python version: {sys.version.split()[0]}")
    print(f"  Python engine:  {platform.python_implementation()}")


def run_smalltalk_demo() -> None:
    """Run the Smalltalk bridge demo against a configured GemStone stone."""
    with example_session(transaction_policy=MANUAL_POLICY) as session:
        facade = GemStoneSessionFacade(session)
        smalltalk = SmalltalkBridge(session)
        settings = smalltalk.StringKeyValueDictionary.new()
        settings["status"] = "ok"
        now = smalltalk.DateAndTime.now()

        print("Smalltalk")
        print(f"  SystemRepository.name = {smalltalk['SystemRepository'].name()}")
        print(f"  Array new: 3          = {smalltalk.Array.new_(3)}")
        print(f"  settings['status']    = {settings['status']!r}")
        print(f"  DateAndTime.now.year  = {now.year()}")

        print("\nGemStone session facade")
        facade["MiscDemo"] = {"status": "ok"}
        facade.commit_transaction()
        print(f"  persistent_root['MiscDemo'] = {facade['MiscDemo']['status']!r}")


def hello_main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the standalone hello demo."""
    if argv:
        raise SystemExit("gemstone-hello does not accept arguments")
    run_hello()
    return 0


def smalltalk_demo_main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the standalone Smalltalk demo."""
    if argv:
        raise SystemExit("gemstone-smalltalk-demo does not accept arguments")
    run_smalltalk_demo()
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the aggregate `gemstone-examples` parser."""
    parser = argparse.ArgumentParser(
        prog="gemstone-examples",
        description="Run packaged gemstone-py example commands.",
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.required = True
    subparsers.add_parser("hello", help="Print Python runtime information.")
    subparsers.add_parser(
        "smalltalk-demo",
        help="Run the Smalltalk bridge demo against GemStone.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch packaged example subcommands."""
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command == "hello":
        run_hello()
        return 0
    if args.command == "smalltalk-demo":
        run_smalltalk_demo()
        return 0
    raise AssertionError(f"Unhandled command: {args.command}")


def main_entry() -> None:
    """Console-script wrapper for `gemstone-examples`."""
    raise SystemExit(main())


def hello_entry() -> None:
    """Console-script wrapper for `gemstone-hello`."""
    raise SystemExit(hello_main())


def smalltalk_demo_entry() -> None:
    """Console-script wrapper for `gemstone-smalltalk-demo`."""
    raise SystemExit(smalltalk_demo_main())
