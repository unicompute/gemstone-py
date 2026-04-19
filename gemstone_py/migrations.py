"""
migrations.py — Reusable Migration base class for GemStone schema migrations.

This module provides a concrete migration lifecycle for translated example
scripts and application code:
  - `up(session)`   — forward migration (v1 → v2)
  - `down(session)` — rollback (v2 → v1), optional
  - `run(session)`  — run up() with commit-conflict retry and progress logging
  - `rollback(session)` — run down() with retry

Usage
-----
    import gemstone_py as gemstone
    from gemstone_py.migrations import Migration
    from gemstone_py.persistent_root import PersistentRoot

    class AddWordCount(Migration):
        description = "Add word_count field to BlogPosts"
        chunk_size  = 50      # commit every N objects (default: 100)

        def up(self, session):
            from gemstone_py.persistent_root import PersistentRoot
            root = PersistentRoot(session)
            posts = root.get('BlogPosts') or {}
            for post_id in posts.keys():
                post = posts[post_id]
                if 'word_count' not in post.keys():
                    text = post.get('text', '')
                    post['word_count'] = str(len(text.split()))
            # run() handles committing

    with gemstone.GemStoneSession() as s:
        AddWordCount().run(s)
"""

PORTING_STATUS = "plain_gemstone_port"
RUNTIME_REQUIREMENT = "Works on plain GemStone images over GCI"

import sys
import time
from typing import Optional

import gemstone_py as gemstone


class MigrationError(Exception):
    pass


class Migration:
    """
    Abstract base class for GemStone schema migrations.

    Subclasses must implement `up(session)`.  `down(session)` is optional
    (override for reversible migrations).

    Class attributes
    ----------------
    description : str
        Human-readable summary printed during run.
    chunk_size : int
        How many objects to process per commit.  Smaller values reduce
        memory pressure and conflict windows; larger values are faster.
        Default: 100.
    max_retries : int
        Maximum commit attempts before giving up (default: 10).
    """

    description: str = ''
    chunk_size:  int = 100
    max_retries: int = 10

    # ------------------------------------------------------------------
    # Subclass interface
    # ------------------------------------------------------------------

    def up(self, session: gemstone.GemStoneSession) -> None:
        """
        Apply the migration.  Called by run().

        Make changes to GemStone objects here.  Do NOT commit inside this
        method — run() handles commits with conflict retry.

        Raise MigrationError to abort.
        """
        raise NotImplementedError(
            f"{type(self).__name__}.up() is not implemented"
        )

    def down(self, session: gemstone.GemStoneSession) -> None:
        """
        Roll back the migration.  Called by rollback().

        Optional — override for reversible migrations.
        The default implementation raises MigrationError.
        """
        raise MigrationError(
            f"{type(self).__name__} does not support rollback"
        )

    # ------------------------------------------------------------------
    # Chunked iteration helper
    # ------------------------------------------------------------------

    def each_in_chunks(self, session: gemstone.GemStoneSession,
                       class_name: str, callback, *,
                       chunk_size: Optional[int] = None,
                       wrap: bool = False) -> int:
        """
        Iterate over all instances of `class_name` in chunks, calling
        `callback(session, instance)` for each, committing every `chunk_size`
        objects.

        Parameters
        ----------
        session : GemStoneSession
        class_name : str
            GemStone class name (e.g. 'RcCounter').
        callback : callable(session, instance) → None
            Called for each instance. By default `instance` is a raw OOP
            integer for compatibility. With `wrap=True`, it is the same
            natural Python value or sendable proxy used by `PersistentRoot`.
        chunk_size : int, optional
            Override the class-level chunk_size for this call.
        wrap : bool, default False
            When True, iterate wrapped objects instead of raw OOP integers.

        Returns
        -------
        int
            Total number of objects processed.
        """
        from gemstone_py.concurrency import list_instances

        n = chunk_size or self.chunk_size
        instances = list_instances(session, class_name, wrap=wrap)
        total = 0
        for i, instance in enumerate(instances, 1):
            callback(session, instance)
            total += 1
            if i % n == 0:
                self._commit_with_retry(session)
                self._log(f"  committed chunk ({i}/{len(instances)})")
        if total % n != 0:
            self._commit_with_retry(session)
        return total

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def run(self, session: gemstone.GemStoneSession) -> None:
        """
        Run the migration: call up(), then commit with retry.

        Prints progress to stdout.
        """
        name = self.description or type(self).__name__
        self._log(f"[migration] {name}")
        t0 = time.monotonic()
        session.abort()        # fresh view before we start
        self.up(session)
        self._commit_with_retry(session)
        elapsed = time.monotonic() - t0
        self._log(f"[migration] done in {elapsed:.2f}s")

    def rollback(self, session: gemstone.GemStoneSession) -> None:
        """
        Roll back the migration: call down(), then commit with retry.
        """
        name = self.description or type(self).__name__
        self._log(f"[migration] rollback {name}")
        session.abort()
        self.down(session)
        self._commit_with_retry(session)
        self._log(f"[migration] rollback done")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _commit_with_retry(self, session: gemstone.GemStoneSession) -> None:
        """
        Commit with up to max_retries attempts on conflict.

        On a commit conflict the session's pending changes are still live
        (GciCommit returning False does not roll them back).  We simply
        abort to get a fresh server view and then retry the commit.  We do
        NOT call up() again — the changes written by up() are still present
        in the session's object space and will be included in the retry.
        """
        from gemstone_py.concurrency import commit as _commit, CommitConflictError
        for attempt in range(1, self.max_retries + 1):
            try:
                _commit(session)
                return
            except CommitConflictError:
                if attempt == self.max_retries:
                    raise MigrationError(
                        f"Migration commit failed after {self.max_retries} attempts"
                    )
                session.abort()
                # Do NOT re-call up() here — changes are still in the session
                # after a failed commit; abort gives us a fresh server view
                # and the next commit attempt will include them.

    @staticmethod
    def _log(msg: str) -> None:
        print(msg, flush=True)
