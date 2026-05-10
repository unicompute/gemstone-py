"""Run typed OOP and typed GSCollection query examples.

This module expects the usual GemStone environment variables. Run it from the
repository root with:

    python -m examples.typed_access.typed_oops_and_queries
"""

from __future__ import annotations

import time
import uuid
from typing import Protocol

from gemstone_py import GemStoneConfig, GemStoneSession, TransactionPolicy, gemstone_class
from gemstone_py.gsquery import GSCollection


@gemstone_class("Date")
class GemStoneDate(Protocol):
    @property
    def printString(self) -> str:
        """GemStone Date print string."""
        ...


class BlogPostRecord(Protocol):
    title: str
    status: str
    timestamp: float


def show_typed_oop(config: GemStoneConfig) -> None:
    with GemStoneSession(config=config, transaction_policy=TransactionPolicy.ABORT_ON_EXIT) as session:
        today = session.execute_typed("Date today", GemStoneDate)  # type: ignore[type-abstract]
        print(f"typed OOP class = {today.gemstone_class_name}")
        print(f"typed proxy printString = {today.proxy().printString}")


def show_typed_query(config: GemStoneConfig) -> None:
    name = f"TypedFeaturePosts_{uuid.uuid4().hex}"
    posts = GSCollection(name, config=config)
    try:
        posts.bulk_insert(
            [
                {
                    "@title": "Async GemStone",
                    "@status": "published",
                    "@timestamp": time.time(),
                },
                {
                    "@title": "Draft typed access",
                    "@status": "draft",
                    "@timestamp": time.time() - 60,
                },
            ]
        )
        posts.add_index("@status")

        published = posts.query(BlogPostRecord).where(
            lambda post: post.status == "published"
        ).all()
        for post in published:
            print(f"published: {post.title} ({post.status})")
    finally:
        GSCollection.drop(name, config=config)


def main() -> None:
    config = GemStoneConfig.from_env()
    show_typed_oop(config)
    show_typed_query(config)


if __name__ == "__main__":
    main()
