from __future__ import annotations

import importlib.util
import unittest


@unittest.skipIf(
    importlib.util.find_spec("fastapi") is None,
    "FastAPI is not installed",
)
@unittest.skipIf(
    importlib.util.find_spec("httpx") is None,
    "FastAPI TestClient dependencies are not installed",
)
class CodegenDemoAppTests(unittest.TestCase):
    def test_generated_wrapper_fastapi_routes(self) -> None:
        from fastapi.testclient import TestClient

        from examples.typed_access.codegen_demo import app as demo_app

        class FakeAsyncSession:
            def __init__(self) -> None:
                self.sources: list[str] = []
                self.performed: list[tuple[int, str, tuple[int, ...]]] = []

            async def execute_oop(self, source: str) -> int:
                self.sources.append(source)
                return 0xB00

            async def perform_value(self, receiver: int, selector: str, *args: int) -> str:
                self.performed.append((receiver, selector, args))
                return "confirmed"

        fake_session = FakeAsyncSession()

        async def fake_get_gemstone() -> object:
            yield fake_session

        demo_app.app.dependency_overrides[demo_app.get_gemstone] = fake_get_gemstone
        try:
            with TestClient(demo_app.app) as client:
                index = client.get("/")
                booking = client.get("/bookings/B-1001")
                docs = client.get("/docs")
        finally:
            demo_app.app.dependency_overrides.clear()

        self.assertEqual(index.status_code, 200)
        self.assertEqual(
            index.json(),
            {
                "name": "gemstone-py codegen demo",
                "endpoints": {
                    "booking": "/bookings/{booking_id}",
                    "docs": "/docs",
                    "openapi": "/openapi.json",
                },
            },
        )
        self.assertEqual(booking.status_code, 200)
        self.assertEqual(booking.json(), {"booking_id": "B-1001", "status": "confirmed"})
        self.assertEqual(docs.status_code, 200)
        self.assertEqual(fake_session.sources, ["OkzBooking findById: 'B-1001'"])
        self.assertEqual(fake_session.performed, [(0xB00, "status", ())])

    def test_codegen_demo_runner_uses_shared_fastapi_runner(self) -> None:
        from unittest import mock

        from examples.typed_access.codegen_demo import run

        with mock.patch("examples.typed_access.codegen_demo.run.main", return_value=0) as main:
            result = run.main_entry()

        self.assertEqual(result, 0)
        main.assert_called_once_with(
            app_path="examples.typed_access.codegen_demo.app:app",
            factory=False,
            module_name="examples.typed_access.codegen_demo.run",
        )


if __name__ == "__main__":
    unittest.main()
