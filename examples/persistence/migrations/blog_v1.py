"""
BlogPost v1.0 — initial schema.

Stores posts as StringKeyValueDictionaries under PersistentRoot['BlogPosts'].
Each post has: id (str), title (str), text (str).

Run this once to set up the store, then run write_posts.py to add data.
"""

PORTING_STATUS = "translated_example"
RUNTIME_REQUIREMENT = "Runs as translated example code on plain GemStone images or standard Python web stacks"

import uuid

from gemstone_py.example_support import example_session
from gemstone_py.persistent_root import PersistentRoot

SCHEMA_VERSION = '1.0'
STORE_KEY      = 'BlogPosts'


def setup(s):
    root = PersistentRoot(s)
    if STORE_KEY not in root:
        root[STORE_KEY] = {}          # empty StringKeyValueDictionary
        print(f'  created {STORE_KEY!r} store (schema v{SCHEMA_VERSION})')
    else:
        print(f'  {STORE_KEY!r} already exists')


def all_posts(s):
    root = PersistentRoot(s)
    col  = root[STORE_KEY]
    posts = []
    for k in col.keys():
        rec = col[k]
        posts.append({field: rec[field] for field in rec.keys()})
    return posts


def new_post(s, title: str, text: str) -> dict:
    post = {
        'id':    str(uuid.uuid4()),
        'title': title,
        'text':  text,
    }
    root = PersistentRoot(s)
    col  = root[STORE_KEY]
    col[post['id']] = post
    return post


if __name__ == '__main__':
    with example_session() as s:
        setup(s)
        print(f'  schema v{SCHEMA_VERSION} initialised')
