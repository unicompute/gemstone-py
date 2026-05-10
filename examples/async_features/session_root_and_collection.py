"""Run async session, persistent-root, and GSCollection examples.

This module expects the usual GemStone environment variables. Run it from the
repository root with:

    python -m examples.async_features.session_root_and_collection
"""

from __future__ import annotations

import asyncio
import uuid

from gemstone_py.aio import AsyncGSCollection, AsyncPersistentRoot, AsyncSession
from gemstone_py.example_support import example_config


async def run_async_session_example() -> None:
    config = example_config()
    root_key = f"AsyncFeatureExample_{uuid.uuid4().hex}"
    collection_name = f"AsyncFeaturePeople_{uuid.uuid4().hex}"

    async with AsyncSession.connect(config=config) as session:
        async with session.transaction():
            root = AsyncPersistentRoot(session)
            await root.set(root_key, {"status": "async", "count": 2})

        async with session.transaction():
            root = session.root()
            saved = await root.get(root_key)
            print(f"root[{root_key!r}] = {saved}")

        ref = await session.execute_managed("OrderedCollection new")
        try:
            first = await session.new_string("from async")
            await ref.send("add:", first)
            print(f"managed async OOP = {await ref.print_string()}")
        finally:
            await ref.close()

        async with session.transaction():
            root = session.root()
            await root.delete(root_key)

    collection = AsyncGSCollection(collection_name, config=config)
    try:
        await collection.bulk_insert(
            [
                {"@name": "Ada", "@status": "active"},
                {"@name": "Grace", "@status": "inactive"},
                {"@name": "Edsger", "@status": "active"},
            ]
        )
        await collection.add_index("@status")
        active = await collection.search("@status", "eql", "active")
        print(f"active rows = {active}")
    finally:
        await AsyncGSCollection.drop(collection_name, config=config)
        collection.close()


def main() -> None:
    asyncio.run(run_async_session_example())


if __name__ == "__main__":
    main()
