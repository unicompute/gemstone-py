"""Packaged FastAPI example runner for gemstone-py."""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import os
import shlex
import sys
from collections.abc import Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

DEFAULT_APP_PATH = "gemstone_py.fastapi_example:create_app"
DEFAULT_MODULE_NAME = "gemstone_py.fastapi_example"
FASTAPI_DEPENDENCIES = ("fastapi", "uvicorn")
STARTUP_INSTRUCTIONS_ENV = "GEMSTONE_PY_FASTAPI_EXAMPLE_BASE_URL"
INDEX_BODY_EXAMPLE = (
    '{"name":"gemstone-py FastAPI example","endpoints":'
    '{"health":"/health/gemstone","docs":"/docs","openapi":"/openapi.json"}}'
)


def create_app() -> Any:
    """Create the minimal FastAPI app used by the packaged example."""
    from fastapi import Depends, FastAPI
    from fastapi.responses import JSONResponse

    from gemstone_py import GemStoneConfig, GemStoneConfigurationError
    from gemstone_py.aio import AsyncSession
    from gemstone_py.aio.fastapi import session_dependency

    @asynccontextmanager
    async def lifespan(_app: Any) -> Any:
        asyncio.create_task(print_startup_instructions())
        yield

    app = FastAPI(lifespan=lifespan)
    get_gemstone_session = session_dependency(
        config=GemStoneConfig.from_env(require_credentials=False)
    )

    @app.get("/")  # type: ignore[untyped-decorator]
    async def index() -> dict[str, Any]:
        return {
            "name": "gemstone-py FastAPI example",
            "endpoints": {
                "health": "/health/gemstone",
                "docs": "/docs",
                "openapi": "/openapi.json",
            },
        }

    @app.exception_handler(GemStoneConfigurationError)  # type: ignore[untyped-decorator]
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

    @app.get("/health/gemstone")  # type: ignore[untyped-decorator]
    async def gemstone_health(
        session: AsyncSession = Depends(get_gemstone_session),
    ) -> dict[str, Any]:
        return {"result": await session.eval("3 + 4")}

    return app


def startup_instructions(base_url: str) -> str:
    """Return post-startup verification instructions for the FastAPI example."""
    clean_base_url = base_url.rstrip("/")
    return "\n".join(
        [
            "",
            "• With that server running, test it from a second terminal.",
            "",
            "  Basic checks:",
            "",
            f"  curl -i {clean_base_url}/",
            "",
            "  Expected:",
            "",
            "  HTTP/1.1 200 OK",
            "",
            "  Body should include:",
            "",
            f"  {INDEX_BODY_EXAMPLE}",
            "",
            "  Then test the GemStone endpoint:",
            "",
            f"  curl -i {clean_base_url}/health/gemstone",
            "",
            "  Expected if GemStone credentials/environment are set and the stone is reachable:",
            "",
            '  {"result":7}',
            "",
            "  Also open these in a browser:",
            "",
            f"  {clean_base_url}/",
            f"  {clean_base_url}/docs",
            f"  {clean_base_url}/health/gemstone",
            "",
        ]
    )


async def print_startup_instructions() -> None:
    """Print verification instructions after Uvicorn has completed startup."""
    await asyncio.sleep(0.1)
    base_url = os.environ.get(STARTUP_INSTRUCTIONS_ENV, "http://127.0.0.1:8000")
    print(startup_instructions(base_url), flush=True)


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
            "You are running:",
            f"  {sys.executable}",
            "",
            "For a source checkout, run:",
            "  python3 -m venv .venv",
            "  source .venv/bin/activate",
            '  python -m pip install -e ".[examples]"',
            "  python -m examples.fastapi.run --reload",
            "",
            "For an installed gemstone-py package in an existing environment, run:",
            f'  {pip_command} install "gemstone-py[fastapi]"',
        ]
    )


def repo_venv_python(root: Path | None = None) -> Path | None:
    """Return the repository virtualenv Python when this is a source checkout."""
    checkout_root = root or Path(__file__).resolve().parents[1]
    candidates = (
        checkout_root / ".venv" / "Scripts" / "python.exe",
        checkout_root / ".venv" / "bin" / "python",
    )
    return next((candidate for candidate in candidates if candidate.exists()), None)


def reexec_with_repo_venv(argv: Sequence[str], module_name: str) -> bool:
    """Re-run the example with the local checkout virtualenv when available."""
    python = repo_venv_python()
    if python is None:
        return False
    if python.absolute() == Path(sys.executable).absolute():
        return False

    os.execv(str(python), [str(python), "-m", module_name, *argv])
    return True


def main(
    argv: Sequence[str] | None = None,
    *,
    app_path: str = DEFAULT_APP_PATH,
    factory: bool = True,
    module_name: str = DEFAULT_MODULE_NAME,
) -> int:
    """Run the FastAPI example through uvicorn."""
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    parser = build_parser()
    args = parser.parse_args(raw_argv)

    missing = missing_dependencies()
    if missing:
        if reexec_with_repo_venv(raw_argv, module_name):
            return 0
        print(dependency_help(missing), file=sys.stderr)
        return 2

    import uvicorn

    display_host = "127.0.0.1" if args.host in {"0.0.0.0", "::"} else args.host
    os.environ[STARTUP_INSTRUCTIONS_ENV] = f"http://{display_host}:{args.port}"
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
