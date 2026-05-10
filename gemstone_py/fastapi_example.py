"""Packaged FastAPI example runner for gemstone-py."""

from __future__ import annotations

import argparse
import importlib.util
import shlex
import sys
from collections.abc import Sequence
from typing import Any

DEFAULT_APP_PATH = "gemstone_py.fastapi_example:create_app"
FASTAPI_DEPENDENCIES = ("fastapi", "uvicorn")


def create_app() -> Any:
    """Create the minimal FastAPI app used by the packaged example."""
    from fastapi import Depends, FastAPI
    from fastapi.responses import JSONResponse

    from gemstone_py import GemStoneConfig, GemStoneConfigurationError
    from gemstone_py.aio import AsyncSession
    from gemstone_py.aio.fastapi import session_dependency

    app = FastAPI()
    get_gemstone_session = session_dependency(
        config=GemStoneConfig.from_env(require_credentials=False)
    )

    @app.exception_handler(GemStoneConfigurationError)
    async def gemstone_configuration_error(
        _request: Any,
        exc: GemStoneConfigurationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={
                "error": str(exc),
                "hint": "Set GS_USERNAME and GS_PASSWORD before calling GemStone endpoints.",
            },
        )

    @app.get("/health/gemstone")
    async def gemstone_health(
        session: AsyncSession = Depends(get_gemstone_session),
    ) -> dict[str, Any]:
        return {"result": await session.eval("3 + 4")}

    return app


def missing_dependencies() -> list[str]:
    """Return missing optional modules needed to run the FastAPI example."""
    return [
        dependency
        for dependency in FASTAPI_DEPENDENCIES
        if importlib.util.find_spec(dependency) is None
    ]


def build_parser() -> argparse.ArgumentParser:
    """Build the FastAPI example runner parser."""
    parser = argparse.ArgumentParser(
        prog="gemstone-fastapi-example",
        description="Run the gemstone-py FastAPI example.",
    )
    add_runner_arguments(parser)
    return parser


def add_runner_arguments(parser: argparse.ArgumentParser) -> None:
    """Add shared FastAPI runner arguments to an argparse parser."""
    parser.add_argument("--host", default="127.0.0.1", help="Host for uvicorn.")
    parser.add_argument("--port", type=int, default=8000, help="Port for uvicorn.")
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Restart the server when source files change.",
    )


def dependency_help(missing: Sequence[str]) -> str:
    """Build a clear install hint for missing optional dependencies."""
    missing_list = ", ".join(missing)
    pip_command = f"{shlex.quote(sys.executable)} -m pip"
    return "\n".join(
        [
            f"Missing optional FastAPI dependencies: {missing_list}",
            "",
            "For an installed gemstone-py package, run:",
            f'  {pip_command} install "gemstone-py[fastapi]"',
            "",
            "For a source checkout, run:",
            f'  {pip_command} install -e ".[examples]"',
        ]
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    app_path: str = DEFAULT_APP_PATH,
    factory: bool = True,
) -> int:
    """Run the FastAPI example through uvicorn."""
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    missing = missing_dependencies()
    if missing:
        print(dependency_help(missing), file=sys.stderr)
        return 2

    import uvicorn

    uvicorn.run(
        app_path,
        factory=factory,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


def main_entry() -> None:
    """Console-script wrapper for ``gemstone-fastapi-example``."""
    raise SystemExit(main())


if __name__ == "__main__":
    main_entry()
