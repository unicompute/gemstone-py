from fastapi import Depends, FastAPI

from gemstone_py import GemStoneConfig
from gemstone_py.aio import AsyncSession
from gemstone_py.aio.fastapi import session_dependency

app = FastAPI()
get_gemstone_session = session_dependency(config=GemStoneConfig.from_env())


@app.get("/health/gemstone")
async def gemstone_health(session: AsyncSession = Depends(get_gemstone_session)):
    return {"result": await session.eval("3 + 4")}
