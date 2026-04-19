"""
Blog domain model — SimplePost and SimpleTag — backed by GemStone
via GemStoneModel.
"""

PORTING_STATUS = "translated_example"
RUNTIME_REQUIREMENT = "Runs as translated example code on plain GemStone images or standard Python web stacks"

import time
import gemstone_py as gemstone
from examples.flask.simple_blog.gemstone_model import GemStoneModel


class SimplePost(GemStoneModel):
    collection_key = 'SimplePosts'

    def __init__(self, title: str | dict, text: str | None = None):
        super().__init__()
        if isinstance(title, dict):
            payload = title
            title = payload.get('title', '')
            text = payload.get('text', '')
        self.title     = title
        self.text      = text or ''
        self.timestamp = time.time()
        self.tags: list[str] = []

    def to_dict(self):
        return {
            'title':     self.title,
            'text':      self.text,
            'timestamp': self.timestamp,
            'tags':      ','.join(self.tags),
        }

    @classmethod
    def from_dict(cls, data: dict):
        obj = cls.__new__(cls)
        obj.id        = data.get('id', '')
        obj.title     = data.get('title', '')
        obj.text      = data.get('text', '')
        obj.timestamp = float(data.get('timestamp', 0))
        tags_raw      = data.get('tags', '')
        obj.tags      = [t for t in tags_raw.split(',') if t] if tags_raw else []
        obj.created_at = obj.timestamp
        return obj

    def tag(self, *tags):
        for tag in tags:
            name = getattr(tag, 'name', tag)
            if not name:
                continue
            if name not in self.tags:
                self.tags.append(name)
            post_ids = getattr(tag, 'post_ids', None)
            if post_ids is not None and self.id not in post_ids:
                post_ids.append(self.id)


class SimpleTag(GemStoneModel):
    collection_key = 'SimpleTags'

    def __init__(self, name: str):
        super().__init__()
        self.name     = name
        self.post_ids: list[str] = []

    def to_dict(self):
        return {
            'name':     self.name,
            'post_ids': ','.join(self.post_ids),
        }

    @classmethod
    def from_dict(cls, data: dict):
        obj = cls.__new__(cls)
        obj.id        = data.get('id', '')
        obj.name      = data.get('name', '')
        raw           = data.get('post_ids', '')
        obj.post_ids  = [p for p in raw.split(',') if p] if raw else []
        obj.created_at = 0.0
        return obj

    @classmethod
    def find_by_name(
        cls,
        name: str,
        session: gemstone.GemStoneSession | None = None,
    ):
        return next((t for t in cls.all(session=session) if t.name == name), None)

    def __str__(self):
        return self.name
