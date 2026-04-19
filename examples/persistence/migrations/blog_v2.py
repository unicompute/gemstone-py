"""
BlogPost v2.0 — add 'date' field.

Extends v1 with a 'date' field (POSIX timestamp float, stored as string).
Old posts created without a date have date=None after reading.

Run migrate.py after upgrading to this version to backfill the date field.
"""

PORTING_STATUS = "translated_example"
RUNTIME_REQUIREMENT = "Runs as translated example code on plain GemStone images or standard Python web stacks"

import time
import uuid

from gemstone_py.example_support import READ_POLICY, example_session
from gemstone_py.persistent_root import PersistentRoot

SCHEMA_VERSION = '2.0'
STORE_KEY      = 'BlogPosts'


def all_posts(s):
    root = PersistentRoot(s)
    col  = root[STORE_KEY]
    posts = []
    for k in col.keys():
        rec = col[k]
        post = {field: rec[field] for field in rec.keys()}
        # date may be absent in old records — surface as None
        post.setdefault('date', None)
        posts.append(post)
    return posts


def new_post(s, title: str, text: str, date: float = None) -> dict:
    post = {
        'id':    str(uuid.uuid4()),
        'title': title,
        'text':  text,
        'date':  str(date if date is not None else time.time()),
    }
    root = PersistentRoot(s)
    col  = root[STORE_KEY]
    col[post['id']] = post
    return post


def print_posts(posts):
    for p in posts:
        date_str = p['date'] or 'Unknown'
        if date_str not in ('Unknown', 'None', None):
            try:
                import datetime
                date_str = datetime.datetime.fromtimestamp(
                    float(date_str), tz=datetime.timezone.utc
                ).strftime('%Y-%m-%d')
            except (ValueError, TypeError):
                pass
        print(f'  {p["title"]:<20s}  {date_str}')


if __name__ == '__main__':
    with example_session(transaction_policy=READ_POLICY) as s:
        posts = all_posts(s)
        print(f'  {len(posts)} posts (schema v{SCHEMA_VERSION}):')
        print_posts(posts)
