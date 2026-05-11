"""Packaged Litestar example runner for gemstone-py."""

from __future__ import annotations

import argparse
import importlib.util
import os
import shlex
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from gemstone_py.aio import AsyncSession

DEFAULT_APP_PATH = "gemstone_py.litestar_example:create_app"
DEFAULT_MODULE_NAME = "gemstone_py.litestar_example"
LITESTAR_DEPENDENCIES = ("litestar", "uvicorn")
STARTUP_INSTRUCTIONS_ENV = "GEMSTONE_PY_LITESTAR_EXAMPLE_BASE_URL"
INDEX_BODY_EXAMPLE = (
    '{"name":"gemstone-py Litestar example","framework":"Litestar",'
    '"adapter":"gemstone_py.aio.litestar.session_dependency",'
    '"dependencyInjection":"litestar.di.Provide","endpoints":'
    '{"health":"/health/gemstone","docs":"/schema/swagger","openapi":"/schema/openapi.json"}}'
)


def create_app() -> Any:
    """Create the minimal Litestar app used by the packaged example."""
    from litestar import Litestar, get
    from litestar.di import Provide

    from gemstone_py import GemStoneConfig
    from gemstone_py.aio.litestar import session_dependency

    get_gemstone_session = session_dependency(
        config=GemStoneConfig.from_env(require_credentials=False)
    )

    @get("/")  # type: ignore[untyped-decorator]
    async def index() -> dict[str, Any]:
        return {
            "name": "gemstone-py Litestar example",
            "framework": "Litestar",
            "adapter": "gemstone_py.aio.litestar.session_dependency",
            "dependencyInjection": "litestar.di.Provide",
            "endpoints": {
                "health": "/health/gemstone",
                "docs": "/schema/swagger",
                "openapi": "/schema/openapi.json",
            },
        }

    @get(
        "/health/gemstone",
        dependencies={"session": Provide(get_gemstone_session)},
    )  # type: ignore[untyped-decorator]
    async def gemstone_health(session: AsyncSession) -> dict[str, Any]:
        return {"result": await session.eval("3 + 4")}

    return Litestar(route_handlers=[index, gemstone_health])


def startup_instructions(base_url: str) -> str:
    """Return post-startup verification instructions for the Litestar example."""
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
            f"  {clean_base_url}/schema/swagger",
            f"  {clean_base_url}/health/gemstone",
            "",
        ]
    )


def missing_dependencies() -> list[str]:
    """Return missing optional modules needed to run the Litestar example."""
    return [
        dependency
        for dependency in LITESTAR_DEPENDENCIES
        if importlib.util.find_spec(dependency) is None
    ]


def build_parser() -> argparse.ArgumentParser:
    """Build the Litestar example runner parser."""
    parser = argparse.ArgumentParser(
        prog="gemstone-litestar-example",
        description="Run the gemstone-py Litestar example.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host for uvicorn.")
    parser.add_argument("--port", type=int, default=8000, help="Port for uvicorn.")
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Restart the server when source files change.",
    )
    return parser


def dependency_help(missing: Sequence[str]) -> str:
    """Build a clear install hint for missing optional dependencies."""
    missing_list = ", ".join(missing)
    pip_command = f"{shlex.quote(sys.executable)} -m pip"
    return "\n".join(
        [
            f"Missing optional Litestar dependencies: {missing_list}",
            "",
            "You are running:",
            f"  {sys.executable}",
            "",
            "For a source checkout, run:",
            "  python3 -m venv .venv",
            "  source .venv/bin/activate",
            '  python -m pip install -e ".[examples]"',
            "  python -m examples.litestar.run --reload",
            "",
            "For an installed gemstone-py package in an existing environment, run:",
            f'  {pip_command} install "gemstone-py[litestar]"',
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
    """Run the Litestar example through uvicorn."""
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
    base_url = f"http://{display_host}:{args.port}"
    os.environ[STARTUP_INSTRUCTIONS_ENV] = base_url
    print(startup_instructions(base_url), flush=True)
    uvicorn.run(
        app_path,
        factory=factory,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


def main_entry() -> None:
    """Console-script wrapper for ``gemstone-litestar-example``."""
    raise SystemExit(main())


if __name__ == "__main__":
    main_entry()
