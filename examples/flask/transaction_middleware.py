"""
GemStone transaction middleware for Flask (WSGI).

This middleware wraps each HTTP request in a GemStone transaction:
  - abort_transaction before the request (get a fresh view of the store)
  - commit_transaction after the request if the status is 2xx or 3xx

This module provides the Python/Flask equivalent.  It is a standard WSGI
middleware so it works with any WSGI server (gunicorn, uWSGI, waitress,
the Flask dev server, etc.).

Usage
-----
    from flask import Flask
    from gemstone_py import GemStoneConfig, GemStoneSessionPool, GemStoneThreadLocalSessionProvider
    from examples.flask.transaction_middleware import (
        GemStoneTransactionMiddleware,
        ManagedGemStoneTransactionMiddleware,
    )
    import gemstone_py as gemstone

    app = Flask(__name__)
    config = GemStoneConfig.from_env()

    # Legacy/simple path: one long-lived shared session.
    session = gemstone.GemStoneSession(config=config)
    session.login()
    app.wsgi_app = GemStoneTransactionMiddleware(app.wsgi_app, session)

    # Production path: provider-managed sessions.
    provider = GemStoneSessionPool(
        maxsize=4,
        config=config,
    )
    app.wsgi_app = ManagedGemStoneTransactionMiddleware(app.wsgi_app, provider)

    # Alternative: one session per worker thread.
    thread_provider = GemStoneThreadLocalSessionProvider(config=config)
    app.wsgi_app = ManagedGemStoneTransactionMiddleware(app.wsgi_app, thread_provider)

    if __name__ == '__main__':
        app.run()

Transaction semantics
---------------------
Before each request:
    session.abort()   — discard stale objects, get fresh view of the store

After the response body is fully produced:
    if 2xx or 3xx → session.commit()
    otherwise     → session.abort()

If the commit fails,
the middleware returns a 500 response to the client so the user knows the
write did not persist.

Notes
-----
- A single shared GemStoneSession is NOT thread-safe. For production, prefer
  `ManagedGemStoneTransactionMiddleware` with `GemStoneSessionPool` or
  `GemStoneThreadLocalSessionProvider`.
- The session must already be logged in before wrapping the app.
- Commit failures are logged to stderr; extend _on_commit_error() to
  integrate with your logging framework.
- Responses are buffered before they are sent so commit/abort decisions are
  made after the full request body has been generated but before bytes are
  written to the client.
"""

PORTING_STATUS = "application_adaptation"
RUNTIME_REQUIREMENT = "Works on plain GemStone images; uses Flask or Django"

import sys
import threading
import traceback

import gemstone_py as gemstone


class GemStoneTransactionMiddleware:
    """
    WSGI middleware that wraps each HTTP request in a GemStone transaction.
    """

    def __init__(self, app, session: gemstone.GemStoneSession):
        """
        Parameters
        ----------
        app
            The inner WSGI application.
        session
            A logged-in GemStoneSession.  Must remain valid for the
            lifetime of the server process.
        """
        self._app     = app
        self._session = session

    def __call__(self, environ, start_response):
        return self._process_request(self._session, environ, start_response)

    def _process_request(self, session, environ, start_response):
        """Handle one HTTP request inside a GemStone transaction."""
        # Abort first — gives us a fresh, consistent view of the store.
        try:
            session.abort()
        except gemstone.GemStoneError as e:
            # If abort fails the session is in a bad state; propagate as 500.
            return self._error_response(
                start_response, f"GemStone abort failed: {e}"
            )

        captured = {}

        def _capture_start_response(status, headers, exc_info=None):
            captured['status'] = status
            captured['headers'] = headers
            captured['exc_info'] = exc_info
            return lambda _chunk: None

        try:
            result = self._app(environ, _capture_start_response)
            body = []
            try:
                for chunk in result:
                    body.append(chunk)
            finally:
                close = getattr(result, 'close', None)
                if close is not None:
                    close()
        except Exception:
            # Unhandled exception in the app — don't commit.
            traceback.print_exc()
            self._abort_after_error(session)
            return self._error_response(start_response, "Internal server error")

        status = captured.get('status')
        if status is None:
            self._abort_after_error(session)
            return self._error_response(
                start_response, "WSGI app failed to call start_response"
            )

        if self._committable(self._status_code(status)):
            try:
                session.commit()
            except gemstone.GemStoneError as e:
                self._on_commit_error(e, environ)
                self._abort_after_error(session)
                return self._error_response(
                    start_response, f"GemStone commit failed: {e}"
                )
        else:
            try:
                session.abort()
            except gemstone.GemStoneError as e:
                return self._error_response(
                    start_response, f"GemStone abort failed: {e}"
                )

        start_response(
            captured['status'],
            captured['headers'],
            captured.get('exc_info'),
        )
        return body

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _status_code(status: str) -> int:
        try:
            return int(status.split(' ', 1)[0])
        except (ValueError, AttributeError):
            return 0

    @staticmethod
    def _committable(status: int) -> bool:
        """True for 2xx and 3xx status codes."""
        return status is not None and 200 <= status <= 399

    def _abort_after_error(self, session) -> None:
        try:
            session.abort()
        except gemstone.GemStoneError:
            pass

    def _on_commit_error(self, exc: gemstone.GemStoneError, environ) -> None:
        """Override to integrate with your logger."""
        path = environ.get('PATH_INFO', '?')
        print(f"[GemStone] commit failed for {path}: {exc}", file=sys.stderr)

    @staticmethod
    def _error_response(start_response, message: str):
        body = message.encode('utf-8')
        start_response(
            '500 Internal Server Error',
            [('Content-Type', 'text/plain'),
             ('Content-Length', str(len(body)))],
        )
        return [body]


class NoLockGemStoneTransactionMiddleware(GemStoneTransactionMiddleware):
    """
    WSGI middleware that wraps each HTTP request in a GemStone transaction
    WITHOUT any process-level locking.

    Use this variant when:
    - The WSGI server is single-threaded (e.g. the Flask dev server with
      threaded=False, or a pre-fork server where each worker process has
      its own GemStoneSession).
    - You manage thread safety yourself (e.g. one session per thread via
      threading.local()).

    Compared to LockingGemStoneTransactionMiddleware
    ------------------------------------------------
    - No threading.Lock is acquired — concurrent requests are not serialised.
    - Suitable for pre-forked servers (gunicorn --worker-class sync) where
      each worker process has its own session and never shares it between
      threads.
    - Throughput is higher but you must ensure the GemStoneSession is not
      shared between concurrent threads.

    Usage
    -----
        from examples.flask.transaction_middleware import (
            NoLockGemStoneTransactionMiddleware,
        )
        import gemstone_py as gemstone

        session = gemstone.GemStoneSession(...)
        session.login()

        app.wsgi_app = NoLockGemStoneTransactionMiddleware(app.wsgi_app, session)
    """
    # Inherits __call__ directly from GemStoneTransactionMiddleware with no
    # locking changes — the class exists as an explicit, named choice so that
    # application code clearly documents which concurrency policy is in use.
    pass


class LockingGemStoneTransactionMiddleware(GemStoneTransactionMiddleware):
    """
    WSGI middleware that wraps each HTTP request in a GemStone transaction
    AND serialises concurrent requests through a process-wide mutex.

    This variant uses a process-local mutex to ensure only one thread runs inside
    GemStone at a time.  This is the safe default for multi-threaded WSGI
    servers (gunicorn threads, waitress) when a single GemStoneSession is
    shared.

    Note: the mutex is process-local (in-memory). If you run multiple
    worker *processes* (gunicorn
    with workers > 1) each process has its own session and its own mutex —
    that is fine, because GemStone handles inter-process isolation via
    transactions.

    Usage
    -----
        from examples.flask.transaction_middleware import (
            LockingGemStoneTransactionMiddleware,
        )
        import gemstone_py as gemstone

        session = gemstone.GemStoneSession(...)
        session.login()

        app.wsgi_app = LockingGemStoneTransactionMiddleware(app.wsgi_app, session)

    Compared to GemStoneTransactionMiddleware
    -----------------------------------------
    - Acquires a threading.Lock before aborting; releases it after the
      commit/no-commit decision.
    - Only one request runs inside GemStone at a time per process.
    - Throughput is serialised but correctness is guaranteed even with a
      thread-unsafe GCI session.
    """

    def __init__(self, app, session: gemstone.GemStoneSession):
        super().__init__(app, session)
        self._lock = threading.Lock()

    def __call__(self, environ, start_response):
        """Serialise through the mutex then delegate to the base handler."""
        self._lock.acquire()
        try:
            return super().__call__(environ, start_response)
        finally:
            self._lock.release()


class PooledGemStoneTransactionMiddleware(GemStoneTransactionMiddleware):
    """
    WSGI middleware that borrows one GemStone session per request from a pool.

    This is the production-safe variant when requests may run concurrently and
    you want to avoid a single shared logged-in GCI session.
    """

    def __init__(self, app, session_pool: gemstone.GemStoneSessionPool):
        super().__init__(app, session=None)
        self._session_provider = session_pool

    def __call__(self, environ, start_response):
        session = self._session_provider.acquire()
        try:
            return self._process_request(session, environ, start_response)
        finally:
            self._session_provider.release(session)


class ManagedGemStoneTransactionMiddleware(GemStoneTransactionMiddleware):
    """
    WSGI middleware that borrows one GemStone session per request from any
    session provider implementing `acquire()` / `release()`.

    Supported providers include `GemStoneSessionPool` and
    `GemStoneThreadLocalSessionProvider`.
    """

    def __init__(self, app, session_provider: gemstone.GemStoneSessionProvider):
        super().__init__(app, session=None)
        self._session_provider = session_provider

    def __call__(self, environ, start_response):
        session = self._session_provider.acquire()
        try:
            return self._process_request(session, environ, start_response)
        finally:
            self._session_provider.release(session)


class ThreadLocalGemStoneTransactionMiddleware(ManagedGemStoneTransactionMiddleware):
    """
    Named variant for the common one-session-per-thread provider case.
    """

    def __init__(
        self,
        app,
        session_provider: gemstone.GemStoneThreadLocalSessionProvider,
    ):
        super().__init__(app, session_provider)
