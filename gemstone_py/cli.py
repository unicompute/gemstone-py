"""Installed CLI entry points for gemstone-py demos."""

from __future__ import annotations

import argparse
import platform
import sys
from collections.abc import Sequence

from gemstone_py.example_support import (
    MANUAL_POLICY,
    WRITE_POLICY,
    example_config,
    example_session,
)
from gemstone_py.fastapi_example import add_runner_arguments
from gemstone_py.fastapi_example import main as run_fastapi_example
from gemstone_py.litestar_example import main as run_litestar_example
from gemstone_py.persistent_root import PersistentRoot
from gemstone_py.session_facade import GemStoneSessionFacade
from gemstone_py.smalltalk_bridge import SmalltalkBridge

QUICKSTART_ROOT_KEY = "GemstonePyQuickstart"
EXAMPLE_CATALOG = (
    ("quickstart", "examples/quickstart.py", "Smallest live connection check."),
    ("webstack", "examples/webstack/", "Realistic Flask reference app."),
    ("fastapi", "examples/fastapi/", "Minimal async FastAPI request dependency."),
    ("litestar", "examples/litestar/", "Minimal async Litestar request dependency."),
    ("typed-access", "examples/typed_access/", "Typed OOPs, queries, and codegen."),
    ("lifetime", "examples/lifetime/", "Managed OOP/export-set lifetime examples."),
    ("native-backend", "examples/native_backend/", "ctypes/native backend selection checks."),
    ("cookbook", "examples/cookbook/", "Index of the broader example recipes."),
)


def run_hello() -> None:
    """Print local Python runtime information."""
    print("Hello from:")
    print(f"  Python version: {sys.version.split()[0]}")
    print(f"  Python engine:  {platform.python_implementation()}")


def run_quickstart() -> None:
    """Run the smallest live GemStone connection example."""
    config = example_config()
    with example_session(transaction_policy=WRITE_POLICY) as session:
        print(f"Connected to {config.stone} as {config.username}.")
        print(f"3 + 4 = {session.eval('3 + 4')}")

        root = PersistentRoot(session)
        root[QUICKSTART_ROOT_KEY] = {
            "message": "Hello from Python",
            "stone": config.stone,
        }
        saved = root[QUICKSTART_ROOT_KEY]
        saved_message = saved["message"]
        saved_stone = saved["stone"]

    print(f"Saved {QUICKSTART_ROOT_KEY}: {saved_message} on {saved_stone}")


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


def run_list_examples() -> None:
    """Print the curated example map for new users."""
    print("gemstone-py examples")
    print("  Start with: python -m examples.quickstart")
    print("")
    for name, path, description in EXAMPLE_CATALOG:
        print(f"  {name:<14} {path:<32} {description}")


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
    subparsers.add_parser("list", help="List the curated example map.")
    subparsers.add_parser("hello", help="Print Python runtime information.")
    subparsers.add_parser(
        "quickstart",
        help="Run the smallest live GemStone connection example.",
    )
    subparsers.add_parser(
        "smalltalk-demo",
        help="Run the Smalltalk bridge demo against GemStone.",
    )
    fastapi_parser = subparsers.add_parser(
        "fastapi",
        help="Run the packaged FastAPI example.",
    )
    add_runner_arguments(fastapi_parser)
    litestar_parser = subparsers.add_parser(
        "litestar",
        help="Run the packaged Litestar example.",
    )
    add_runner_arguments(litestar_parser)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch packaged example subcommands."""
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command == "hello":
        run_hello()
        return 0
    if args.command == "list":
        run_list_examples()
        return 0
    if args.command == "quickstart":
        run_quickstart()
        return 0
    if args.command == "smalltalk-demo":
        run_smalltalk_demo()
        return 0
    if args.command == "fastapi":
        fastapi_args = ["--host", args.host, "--port", str(args.port)]
        if args.reload:
            fastapi_args.append("--reload")
        return int(run_fastapi_example(fastapi_args))
    if args.command == "litestar":
        litestar_args = ["--host", args.host, "--port", str(args.port)]
        if args.reload:
            litestar_args.append("--reload")
        return int(run_litestar_example(litestar_args))
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


if __name__ == "__main__":
    main_entry()
