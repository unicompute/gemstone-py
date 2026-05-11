"""Preview the generated Codegen wrapper package without touching checked-in files.

Run from the repository root:

    python -m examples.typed_access.codegen_demo.preview

This is the safest first Codegen example because it only writes to a temporary
directory. Use it before `gemstone-codegen --clean` when you are changing
Protocol definitions and want to inspect what will be generated.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
from tempfile import TemporaryDirectory

from gemstone_py.codegen import generate_package

DEFAULT_MODULE = "examples.typed_access.codegen_demo.models"
DEFAULT_OUTPUT = "examples/typed_access/codegen_demo/generated"


def build_parser() -> argparse.ArgumentParser:
    """Build the preview example parser."""
    parser = argparse.ArgumentParser(
        prog="python -m examples.typed_access.codegen_demo.preview",
        description="Preview generated GemStone wrapper files in a temporary directory.",
    )
    parser.add_argument(
        "--module",
        default=DEFAULT_MODULE,
        help="Protocol module to generate from.",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help="Checked-in output package used for the follow-up command hint.",
    )
    parser.add_argument(
        "--show-source",
        action="store_true",
        help="Print the full generated source instead of a compact file summary.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the offline Codegen preview."""
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    with TemporaryDirectory(prefix="gemstone-py-codegen-") as temp_dir:
        temp_path = Path(temp_dir)
        files = generate_package(args.module, temp_path, clean=True)

        print("gemstone-py Codegen preview")
        print(f"  Protocol module: {args.module}")
        print(f"  Temporary output: {temp_path}")
        print("")
        print("Generated files:")
        for file in files:
            relative = file.path.relative_to(temp_path)
            print(f"  {relative.as_posix():<24} {file.class_name}")
            for warning in file.warnings:
                print(f"    warning: {warning}")

        print("")
        print("Concrete wrapper usage after generation:")
        print("  from examples.typed_access.codegen_demo.generated import OkzBooking")
        print("  booking = OkzBooking.find_by_id(session, 'B-1001')")
        print("  print(booking.status)")
        print("  booking.mark_paid(1_779_912_000)")

        print("")
        print("To update the checked-in generated package:")
        print("  gemstone-codegen \\")
        print(f"    --module {args.module} \\")
        print(f"    --output {args.output} \\")
        print("    --clean")
        print("")
        print("To verify it in CI:")
        print("  gemstone-codegen \\")
        print(f"    --module {args.module} \\")
        print(f"    --output {args.output} \\")
        print("    --check")

        if args.show_source:
            print("")
            print("Full generated source:")
            for file in files:
                print("")
                print(f"# {file.path.relative_to(temp_path).as_posix()}")
                print(file.source)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
