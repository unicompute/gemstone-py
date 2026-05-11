from __future__ import annotations

import asyncio
import importlib
import sys
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Protocol

import gemstone_py as gemstone
from gemstone_py.codegen import generate_package, generate_wrapper, selector_for_method


@gemstone.gemstone_class("CodegenBooking", async_=True)
class CodegenBookingProto(Protocol):
    status: str

    @classmethod
    @gemstone.gemstone_selector("findById:")
    def find_by_id(cls, booking_id: str) -> "CodegenBookingProto":
        ...

    @classmethod
    @gemstone.gemstone_selector("countAll")
    def count_all(cls) -> int:
        ...

    def mark_paid(self, at: int) -> None:
        ...

    def yourself(self) -> "CodegenBookingProto":
        ...

    @gemstone.gemstone_selector("transferTo:byUserId:")
    def transfer(self, user_id: int, by_user_id: int) -> None:
        ...


class FakeSyncSession:
    def __init__(self) -> None:
        self.sources: list[str] = []
        self.value_sources: list[str] = []
        self.performed: list[tuple[int, str, tuple[int, ...]]] = []
        self.performed_oops: list[tuple[int, str, tuple[int, ...]]] = []

    def execute_oop(self, source: str) -> int:
        self.sources.append(source)
        return 0xB00

    def eval(self, source: str) -> int:
        self.value_sources.append(source)
        return 42

    def perform_value(self, receiver: int, selector: str, *args: int) -> str:
        self.performed.append((receiver, selector, args))
        return f"{selector}-result"

    def perform_oop(self, receiver: int, selector: str, *args: int) -> int:
        self.performed_oops.append((receiver, selector, args))
        return 0xB01


class FakeAsyncSession:
    def __init__(self) -> None:
        self.sources: list[str] = []
        self.value_sources: list[str] = []
        self.performed: list[tuple[int, str, tuple[int, ...]]] = []
        self.performed_oops: list[tuple[int, str, tuple[int, ...]]] = []

    async def execute_oop(self, source: str) -> int:
        self.sources.append(source)
        return 0xC00

    async def eval(self, source: str) -> int:
        self.value_sources.append(source)
        return 84

    async def perform_value(self, receiver: int, selector: str, *args: int) -> str:
        self.performed.append((receiver, selector, args))
        return f"{selector}-result"

    async def perform_oop(self, receiver: int, selector: str, *args: int) -> int:
        self.performed_oops.append((receiver, selector, args))
        return 0xC01


class CodegenTests(unittest.TestCase):
    def test_selector_for_method_infers_smalltalk_keywords(self) -> None:
        self.assertEqual(selector_for_method("status", ()), "status")
        self.assertEqual(selector_for_method("find_by_id", ("booking_id",)), "findById:")
        self.assertEqual(
            selector_for_method("transfer_to", ("user_id", "by_user_id")),
            "transferTo:byUserId:",
        )
        self.assertEqual(
            selector_for_method(
                "python_name",
                ("left", "right"),
                explicit="between:and:",
            ),
            "between:and:",
        )
        with self.assertRaises(ValueError):
            selector_for_method("bad", ("left",), explicit="between:and:")

    def test_generate_wrapper_builds_sync_and_async_sources(self) -> None:
        source = generate_wrapper(CodegenBookingProto)

        self.assertIn("class CodegenBooking(TypedOop[Any]):", source)
        self.assertIn("class AsyncCodegenBooking(TypedOop[Any]):", source)
        self.assertIn("def status(self) -> str:", source)
        self.assertIn("def mark_paid(self, at: int) -> None:", source)
        self.assertIn("def yourself(self) -> CodegenBooking:", source)
        self.assertIn("async def yourself(self) -> AsyncCodegenBooking:", source)
        self.assertIn("self.send('markPaid:', at)", source)
        self.assertIn("oop = self.send_oop('yourself')", source)
        self.assertIn("self.send('transferTo:byUserId:', user_id, by_user_id)", source)

    def test_generated_sync_wrapper_builds_smalltalk_sources(self) -> None:
        namespace: dict[str, Any] = {}
        exec(generate_wrapper(CodegenBookingProto), namespace)
        booking_cls = namespace["CodegenBooking"]
        session = FakeSyncSession()

        booking = booking_cls.find_by_id(session, "A'7")
        count = booking_cls.count_all(session)
        status = booking.status
        paid_result = booking.mark_paid(123)
        refreshed = booking.yourself()
        booking.transfer(456, 789)

        self.assertEqual(session.sources, ["CodegenBooking findById: 'A''7'"])
        self.assertEqual(session.value_sources, ["CodegenBooking countAll"])
        self.assertEqual(count, 42)
        self.assertEqual(status, "status-result")
        self.assertIsNone(paid_result)
        self.assertIsInstance(refreshed, booking_cls)
        self.assertEqual(int(refreshed), 0xB01)
        self.assertIs(refreshed.wrapper_type, booking_cls)
        self.assertEqual(
            session.performed,
            [
                (0xB00, "status", ()),
                (0xB00, "markPaid:", (123,)),
                (0xB00, "transferTo:byUserId:", (456, 789)),
            ],
        )
        self.assertEqual(session.performed_oops, [(0xB00, "yourself", ())])

    def test_generated_async_wrapper_calls_async_session(self) -> None:
        namespace: dict[str, Any] = {}
        exec(generate_wrapper(CodegenBookingProto), namespace)
        booking_cls = namespace["AsyncCodegenBooking"]
        session = FakeAsyncSession()

        async def run() -> None:
            booking = await booking_cls.find_by_id(session, "B-8")
            count = await booking_cls.count_all(session)
            status = await booking.status()
            paid_result = await booking.mark_paid(321)
            refreshed = await booking.yourself()
            await booking.transfer(654, 987)
            self.assertEqual(count, 84)
            self.assertEqual(status, "status-result")
            self.assertIsNone(paid_result)
            self.assertIsInstance(refreshed, booking_cls)
            self.assertEqual(int(refreshed), 0xC01)

        asyncio.run(run())

        self.assertEqual(session.sources, ["CodegenBooking findById: 'B-8'"])
        self.assertEqual(session.value_sources, ["CodegenBooking countAll"])
        self.assertEqual(
            session.performed,
            [
                (0xC00, "status", ()),
                (0xC00, "markPaid:", (321,)),
                (0xC00, "transferTo:byUserId:", (654, 987)),
            ],
        )
        self.assertEqual(session.performed_oops, [(0xC00, "yourself", ())])

    def test_generate_package_writes_checked_in_style_modules(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            module_path = root / "models.py"
            module_path.write_text(
                textwrap.dedent(
                    """
                    from typing import Protocol
                    from gemstone_py import gemstone_class, gemstone_selector

                    @gemstone_class("CodegenCustomer")
                    class CustomerProto(Protocol):
                        name: str

                    @gemstone_class("CodegenInvoice")
                    class InvoiceProto(Protocol):
                        total: int

                        @classmethod
                        @gemstone_selector("findById:")
                        def find_by_id(cls, invoice_id: str) -> "InvoiceProto":
                            ...

                        def buyer(self) -> "CustomerProto":
                            ...
                    """
                ),
                encoding="utf-8",
            )
            output = root / "generated"
            output.mkdir()
            stale = output / "stale.py"
            stale.write_text(
                '"""Generated GemStone wrappers.\n\n'
                "Regenerate with `gemstone-codegen`; do not edit by hand.\n"
                '"""\n',
                encoding="utf-8",
            )
            stale_stub = output / "stale.pyi"
            stale_stub.write_text(
                '"""Generated GemStone wrappers.\n\n'
                "Regenerate with `gemstone-codegen`; do not edit by hand.\n"
                '"""\n',
                encoding="utf-8",
            )
            sys.path.insert(0, str(root))
            try:
                files = generate_package("models", output, clean=True)
                checked = generate_package("models", output, check=True)
                importlib.invalidate_caches()
                generated_package = importlib.import_module("generated")
                invoice = generated_package.Invoice(0xD00, session=FakeSyncSession())
                buyer = invoice.buyer()
                buyer_is_customer = isinstance(buyer, generated_package.Customer)
                buyer_oop = int(buyer)
            finally:
                sys.path.remove(str(root))
                for module_name in list(sys.modules):
                    if module_name == "models" or module_name.startswith("generated"):
                        sys.modules.pop(module_name, None)

        self.assertTrue(all(file.up_to_date for file in files))
        self.assertTrue(all(file.up_to_date for file in checked))
        self.assertTrue(any(file.path.name == "invoice.py" for file in files))
        self.assertTrue(any(file.path.name == "invoice.pyi" for file in files))
        self.assertTrue(any(file.path.name == "customer.py" for file in files))
        self.assertTrue(any(file.path.name == "customer.pyi" for file in files))
        self.assertTrue(any(file.path.name == "__init__.pyi" for file in files))
        self.assertTrue(any(file.path.name == "py.typed" for file in files))
        self.assertFalse(stale.exists())
        self.assertFalse(stale_stub.exists())
        self.assertTrue(buyer_is_customer)
        self.assertEqual(buyer_oop, 0xB01)

    def test_repository_codegen_check_script_tracks_demo_wrapper(self) -> None:
        script = Path("scripts/check_codegen.sh").read_text(encoding="utf-8")
        ci_script = Path("scripts/run_ci_checks.sh").read_text(encoding="utf-8")
        pre_commit_hooks = Path(".pre-commit-hooks.yaml").read_text(encoding="utf-8")

        self.assertIn("--module examples.typed_access.codegen_demo.models", script)
        self.assertIn("--output examples/typed_access/codegen_demo/generated", script)
        self.assertIn("--check", script)
        self.assertIn("scripts/check_codegen.sh", ci_script)
        self.assertIn("gemstone-codegen-check", pre_commit_hooks)


if __name__ == "__main__":
    unittest.main()
