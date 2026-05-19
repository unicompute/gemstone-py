#!/usr/bin/env python3
"""Smoke-test the gemstone-py-native Rust-core bridge.

By default this script verifies the installed native extension exposes the
gemstone-rs shared-core reports. Set GS_RUN_LIVE=1, or pass --require-live, to
exercise a real GemStone/S login through RustCoreSession.
"""

from __future__ import annotations

import argparse
import json
import os
import sys


def _load_native_module():
    try:
        from gemstone_py_native import _gci
    except Exception as exc:  # pragma: no cover - import failure path is CLI behavior.
        raise SystemExit(
            "gemstone_py_native._gci is not importable; install gemstone-py-native "
            "or run this inside the native wheel verification environment"
        ) from exc
    return _gci


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def _check_report_surface(_gci) -> None:
    _expect(_gci.native_implementation() == "pyo3", "expected PyO3 native extension")
    _expect(
        _gci.rust_core_implementation() == "gemstone-rs",
        "expected gemstone-rs Rust-core implementation",
    )
    _expect(hasattr(_gci, "RustCoreSession"), "missing RustCoreSession")

    capabilities = json.loads(_gci.rust_core_capabilities_json())
    migration = json.loads(_gci.rust_core_migration_json())
    conformance = json.loads(_gci.rust_core_conformance_json())
    handoff = json.loads(_gci.rust_core_handoff_json())

    _expect(capabilities["name"] == "gemstone-py-native adapter contract", "bad capabilities")
    _expect("eval" in capabilities["operations"], "capabilities missing eval")
    _expect(migration["targetPackage"] == "gemstone-py-native", "bad migration target")
    _expect(migration["doneCount"] >= 3, "migration report does not show wired bridge")
    _expect(
        "RustCoreSession" in json.dumps(migration, sort_keys=True),
        "migration report does not mention RustCoreSession",
    )
    _expect("eval_json" in conformance["nativeSessionMethods"], "missing eval_json")
    _expect("perform_json" in conformance["nativeSessionMethods"], "missing perform_json")
    _expect(handoff["adapterModule"] == "gemstone_rs::py_native", "bad handoff adapter")


def _check_live_session(_gci) -> None:
    session = _gci.RustCoreSession.login_from_env()
    try:
        _expect(session.session_id() >= 0, "invalid session id")
        _expect(session.eval_smallint("3 + 4") == 7, "3 + 4 did not return 7")

        value = json.loads(session.eval_json("3 + 4"))
        _expect(value == {"kind": "smallInt", "value": 7}, "unexpected eval_json payload")

        smallint_oop = session.value_to_oop_smallint(7)
        printed = json.loads(session.perform_json(smallint_oop, "printString", []))
        _expect(printed == {"kind": "string", "value": "7"}, "unexpected printString")

        object_oop = session.resolve("Object")
        _expect(isinstance(object_oop, int) and object_oop > 0, "Object did not resolve")

        string_oop = session.new_string("gemstone-py-native rust core")
        _expect(
            session.fetch_string(string_oop) == "gemstone-py-native rust core",
            "string round trip failed",
        )
        session.add_to_export_set(string_oop)
        session.remove_from_export_set(string_oop)

        global_name = f"GemStonePyRustCoreSmoke{os.getpid()}"
        session.global_put_string(global_name, "rust-core-live")
        fetched = session.global_get(global_name)
        _expect(session.fetch_string(fetched) == "rust-core-live", "global string read failed")
        _expect(session.needs_commit(), "global write did not mark transaction dirty")
        session.abort()
        _expect(not session.in_transaction(), "abort left the session in a transaction")
        session.commit()
    finally:
        session.logout()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify gemstone-py-native RustCoreSession and shared-core reports."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Verify the extension/report surface only; never login to GemStone.",
    )
    parser.add_argument(
        "--require-live",
        action="store_true",
        help="Fail unless GS_RUN_LIVE=1 and live RustCoreSession checks pass.",
    )
    args = parser.parse_args(argv)

    _gci = _load_native_module()
    _check_report_surface(_gci)

    live_enabled = os.environ.get("GS_RUN_LIVE") == "1"
    if args.dry_run or not live_enabled:
        if args.require_live and not live_enabled:
            raise SystemExit("GS_RUN_LIVE=1 is required for live Rust-core smoke")
        print("native Rust-core smoke dry-run passed")
        return 0

    _check_live_session(_gci)
    print("native Rust-core live smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
