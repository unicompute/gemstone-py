"""
Write sample posts using the current schema.

Run after blog_v1.py (or blog_v2.py) to add five sample posts.
"""

PORTING_STATUS = "translated_example"
RUNTIME_REQUIREMENT = "Runs as translated example code on plain GemStone images or standard Python web stacks"

from examples.persistence.migrations import blog_v1 as blog
from gemstone_py.example_support import example_session

with example_session() as s:
    for i in range(5):
        p = blog.new_post(s, f'Title {i}', f'Text {i}')
        print(f'  wrote post {p["id"][:8]}…  {p["title"]!r}')
    print(f'  {len(blog.all_posts(s))} posts total')
