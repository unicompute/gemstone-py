from __future__ import annotations

import asyncio
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

    def mark_paid(self, at: int) -> None:
        ...

    @gemstone.gemstone_selector("transferTo:byUserId:")
    def transfer(self, user_id: int, by_user_id: int) -> None:
        ...


class FakeSyncSession:
    def __init__(self) -> None:
        self.sources: list[str] = []
        self.performed: list[tuple[int, str, tuple[int, ...]]] = []

    def execute_oop(self, source: str) -> int:
        self.sources.append(source)
        return 0xB00

    def perform_value(self, receiver: int, selector: str, *args: int) -> str:
        self.performed.append((receiver, selector, args))
        return f"{selector}-result"


class FakeAsyncSession:
    def __init__(self) -> None:
        self.sources: list[str] = []
        self.performed: list[tuple[int, str, tuple[int, ...]]] = []

    async def execute_oop(self, source: str) -> int:
        self.sources.append(source)
        return 0xC00

    async def perform_value(self, receiver: int, selector: str, *args: int) -> str:
        self.performed.append((receiver, selector, args))
        return f"{selector}-result"


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
        self.assertIn("return self.send('status')", source)
        self.assertIn("return self.send('markPaid:', at)", source)
        self.assertIn("return self.send('transferTo:byUserId:', user_id, by_user_id)", source)

    def test_generated_sync_wrapper_builds_smalltalk_sources(self) -> None:
        namespace: dict[str, Any] = {}
        exec(generate_wrapper(CodegenBookingProto), namespace)
        booking_cls = namespace["CodegenBooking"]
        session = FakeSyncSession()

        booking = booking_cls.find_by_id(session, "A'7")
        status = booking.status
        booking.mark_paid(123)
        booking.transfer(456, 789)

        self.assertEqual(session.sources, ["CodegenBooking findById: 'A''7'"])
        self.assertEqual(status, "status-result")
        self.assertEqual(
            session.performed,
            [
                (0xB00, "status", ()),
                (0xB00, "markPaid:", (123,)),
                (0xB00, "transferTo:byUserId:", (456, 789)),
            ],
        )

    def test_generated_async_wrapper_calls_async_session(self) -> None:
        namespace: dict[str, Any] = {}
        exec(generate_wrapper(CodegenBookingProto), namespace)
        booking_cls = namespace["AsyncCodegenBooking"]
        session = FakeAsyncSession()

        async def run() -> None:
            booking = await booking_cls.find_by_id(session, "B-8")
            status = await booking.status()
            await booking.mark_paid(321)
            self.assertEqual(status, "status-result")

        asyncio.run(run())

        self.assertEqual(session.sources, ["CodegenBooking findById: 'B-8'"])
        self.assertEqual(
            session.performed,
            [
                (0xC00, "status", ()),
                (0xC00, "markPaid:", (321,)),
            ],
        )

    def test_generate_package_writes_checked_in_style_modules(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            module_path = root / "models.py"
            module_path.write_text(
                textwrap.dedent(
                    """
                    from typing import Protocol
                    from gemstone_py import gemstone_class, gemstone_selector

                    @gemstone_class("CodegenInvoice")
                    class InvoiceProto(Protocol):
                        total: int

                        @classmethod
                        @gemstone_selector("findById:")
                        def find_by_id(cls, invoice_id: str) -> "InvoiceProto":
                            ...
                    """
                ),
                encoding="utf-8",
            )
            output = root / "generated"
            sys.path.insert(0, str(root))
            try:
                files = generate_package("models", output)
                checked = generate_package("models", output, check=True)
            finally:
                sys.path.remove(str(root))
                sys.modules.pop("models", None)

        self.assertTrue(all(file.up_to_date for file in files))
        self.assertTrue(all(file.up_to_date for file in checked))
        self.assertTrue(any(file.path.name == "invoice.py" for file in files))


if __name__ == "__main__":
    unittest.main()
