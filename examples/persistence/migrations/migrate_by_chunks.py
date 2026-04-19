"""
Chunked migration.

Demonstrates how to migrate a large persistent collection in bounded-memory
chunks, committing after each page.  This avoids holding the entire
collection in memory or in a single large transaction.

The migration adds a 'word_count' field to every BlogPost that is missing
it (i.e. posts written by the v1 schema).  It processes posts in pages of
CHUNK_SIZE, committing after each chunk.

This pattern is important for production migrations because:
  - Commit conflicts affect only the current chunk, not the whole dataset.
  - Memory is bounded regardless of collection size.
  - Progress survives a crash (already-migrated chunks stay committed).
  - Keeps the migration bounded and restart-friendly.

Run order:
    python3 blog_v1.py         # set up schema
    python3 write_posts.py     # seed sample data
    python3 migrate_by_chunks.py  # backfill word_count

Then verify with:
    python3 -c "
    from gemstone_py.example_support import READ_POLICY, example_session
    from gemstone_py.persistent_root import PersistentRoot
    with example_session(transaction_policy=READ_POLICY) as s:
        root = PersistentRoot(s)
        col  = root['BlogPosts']
        for k in col.keys():
            rec = col[k]
            print(rec['title'], '->', rec.get('word_count', 'MISSING'))
    "
"""

PORTING_STATUS = "translated_example"
RUNTIME_REQUIREMENT = "Runs as translated example code on plain GemStone images or standard Python web stacks"

import time

import gemstone_py as gemstone
from gemstone_py.example_support import MANUAL_POLICY, example_session
from gemstone_py.persistent_root import PersistentRoot

STORE_KEY  = 'BlogPosts'
CHUNK_SIZE = 50          # posts per commit — tune to available memory / lock budget


def _needs_migration(rec) -> bool:
    """Return True if this post is missing the word_count field."""
    try:
        rec['word_count']
        return False
    except (KeyError, Exception):
        return True


def _word_count(text: str) -> int:
    return len(text.split())


def migrate_by_chunks() -> None:
    """
    Backfill 'word_count' on every BlogPost record, CHUNK_SIZE at a time.
    """
    t_start     = time.perf_counter()
    total       = 0
    migrated    = 0
    chunk_num   = 0

    with example_session(transaction_policy=MANUAL_POLICY) as s:
        root = PersistentRoot(s)

        if STORE_KEY not in root:
            print(f"  {STORE_KEY!r} not found — run blog_v1.py and write_posts.py first")
            return

        col  = root[STORE_KEY]
        keys = col.keys()   # snapshot of keys at migration start
        total = len(keys)

        chunk = []
        for key in keys:
            chunk.append(key)
            if len(chunk) >= CHUNK_SIZE:
                _process_chunk(s, col, chunk)
                migrated += len(chunk)
                chunk_num += 1
                print(f"  chunk {chunk_num:3d}: committed {migrated}/{total} posts")
                chunk = []

        # Tail chunk (fewer than CHUNK_SIZE)
        if chunk:
            _process_chunk(s, col, chunk)
            migrated += len(chunk)
            chunk_num += 1
            print(f"  chunk {chunk_num:3d}: committed {migrated}/{total} posts (final)")

    elapsed = time.perf_counter() - t_start
    print(f"\n  Done.  {total} posts processed in {chunk_num} chunks  ({elapsed:.3f}s)")


def _process_chunk(s: gemstone.GemStoneSession, col, keys: list) -> None:
    """
    Backfill word_count on the posts identified by `keys`, then commit.

    Each post is a GsDict (live GemStone StringKeyValueDictionary proxy).
    Writing to it via col[key][field] = value is immediately sent to GemStone.
    The commit at the end of each chunk makes the writes durable.
    """
    for key in keys:
        try:
            rec = col[key]
            if _needs_migration(rec):
                text = rec.get('text', '')
                rec['word_count'] = str(_word_count(text))
        except Exception as e:
            print(f"  WARNING: skipping key {key!r}: {e}")

    # Commit this chunk — GemStoneSession.__exit__ would also commit, but we
    # commit explicitly here to checkpoint each chunk independently so a crash
    # only loses at most one chunk worth of work.
    s.commit()


if __name__ == '__main__':
    print("Chunked migration: backfilling word_count on BlogPosts")
    print("─" * 56)
    migrate_by_chunks()
