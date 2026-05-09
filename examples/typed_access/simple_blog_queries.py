"""Typed query examples for the GemStone-backed simple blog records."""

from __future__ import annotations

from typing import Protocol

from gemstone_py import GemStoneConfig, GemStoneSession
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
