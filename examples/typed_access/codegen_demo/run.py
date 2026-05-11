"""Run the generated-wrapper FastAPI demo with dependency checks."""

from __future__ import annotations

from gemstone_py.fastapi_example import main


def main_entry() -> int:
    """Run ``examples.typed_access.codegen_demo.app:app`` through uvicorn."""
    return main(
        app_path="examples.typed_access.codegen_demo.app:app",
        factory=False,
        module_name="examples.typed_access.codegen_demo.run",
    )


if __name__ == "__main__":
    raise SystemExit(main_entry())
