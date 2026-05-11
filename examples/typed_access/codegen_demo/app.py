"""FastAPI-style usage of generated GemStone wrappers.

Run code generation first:

    gemstone-codegen --module examples.typed_access.codegen_demo.models \
        --output examples/typed_access/codegen_demo/generated
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI

from gemstone_py import GemStoneConfig
from gemstone_py.aio import AsyncSession
from gemstone_py.aio.fastapi import session_dependency

from .generated import AsyncOkzBooking

app = FastAPI(title="gemstone-py codegen demo")
get_gemstone = session_dependency(config=GemStoneConfig.from_env(require_credentials=False))


@app.get("/")
async def index() -> dict[str, Any]:
    """Return the available codegen demo routes."""
    return {
        "name": "gemstone-py codegen demo",
        "endpoints": {
            "booking": "/bookings/{booking_id}",
            "docs": "/docs",
            "openapi": "/openapi.json",
        },
    }


@app.get("/bookings/{booking_id}")
async def booking_status(
    booking_id: str,
    session: AsyncSession = Depends(get_gemstone),
) -> dict[str, str]:
    booking = await AsyncOkzBooking.find_by_id(session, booking_id)
    return {"booking_id": booking_id, "status": str(await booking.status())}
