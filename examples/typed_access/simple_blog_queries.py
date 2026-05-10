"""Typed query examples for the GemStone-backed simple blog records."""

from __future__ import annotations

from typing import Protocol

from gemstone_py import GemStoneConfig, GemStoneSession, gemstone_class
from gemstone_py.gsquery import GSCollection


class BlogPostRecord(Protocol):
    title: str
    status: str
    timestamp: float


def published_posts(
    *,
    config: GemStoneConfig | None = None,
    session: GemStoneSession | None = None,
) -> list[BlogPostRecord]:
    posts = GSCollection("SimplePosts", config=config).query(BlogPostRecord, session=session)
    return posts.where(lambda post: post.status == "published").all()


def recent_published_posts(
    cutoff_timestamp: float,
    *,
    config: GemStoneConfig | None = None,
    session: GemStoneSession | None = None,
) -> list[BlogPostRecord]:
    posts = GSCollection("SimplePosts", config=config).query(BlogPostRecord, session=session)
    return (
        posts.where(lambda post: post.status == "published")
        .where(lambda post: post.timestamp >= cutoff_timestamp)
        .all()
    )


@gemstone_class("Date")
class GemStoneDate(Protocol):
    @property
    def printString(self) -> str:
        """Return GemStone's printable date representation."""
        ...


def typed_today(session: GemStoneSession) -> GemStoneDate:
    """Return today's GemStone Date through a typed OOP runtime proxy."""
    today = session.execute_typed("Date today", GemStoneDate)  # type: ignore[type-abstract]
    return today.proxy()
