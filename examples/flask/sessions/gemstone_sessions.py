"""
GemStone-backed Flask session storage.

This module implements a Flask session interface backed by GemStone's
UserGlobals via PersistentRoot.

Each session is stored as a nested StringKeyValueDictionary under:
    PersistentRoot['FlaskSessions'][session_id] = {key: value, ...}

Usage:
    from examples.flask.sessions.gemstone_sessions import GemStoneSessionInterface
    app.session_interface = GemStoneSessionInterface()
"""

PORTING_STATUS = "application_adaptation"
RUNTIME_REQUIREMENT = "Works on plain GemStone images; uses Flask or Django"

import json
import uuid

from flask.sessions import SessionInterface, SessionMixin
from werkzeug.datastructures import CallbackDict

import gemstone_py as gemstone
from gemstone_py.persistent_root import PersistentRoot

GS_SESSIONS_KEY = 'FlaskSessions'


class GemStoneSession(CallbackDict, SessionMixin):
    def __init__(self, initial=None, sid=None, new=False):
        def on_update(self):
            self.modified = True
        CallbackDict.__init__(self, initial or {}, on_update)
        self.sid      = sid
        self.new      = new
        self.modified = False


class GemStoneSessionInterface(SessionInterface):
    """
    Flask session interface backed by GemStone via PersistentRoot.

    open_session loads a session dict from GemStone and save_session writes
    it back and commits.
    """

    _gemstone_request_session_finalizes = True

    def _store(self, root: PersistentRoot, create: bool = True):
        """Return the FlaskSessions sub-dictionary, optionally creating it."""
        if GS_SESSIONS_KEY not in root:
            if not create:
                return None
            root[GS_SESSIONS_KEY] = {}
        return root[GS_SESSIONS_KEY]

    def open_session(self, app, request):
        sid = request.cookies.get(app.config.get('SESSION_COOKIE_NAME', 'session'))

        if sid:
            with gemstone.session_scope() as s:
                root  = PersistentRoot(s)
                store = self._store(root, create=False)
                if store is not None and sid in store:
                    record = store[sid]
                    data   = {k: record[k] for k in record.keys()}
                    return GemStoneSession(data, sid=sid)

        return GemStoneSession(sid=str(uuid.uuid4()), new=True)

    def save_session(self, app, session, response):
        domain    = self.get_cookie_domain(app)
        path      = self.get_cookie_path(app)
        http_only = self.get_cookie_httponly(app)
        secure    = self.get_cookie_secure(app)

        if not session:
            if session.modified:
                with gemstone.session_scope() as s:
                    root  = PersistentRoot(s)
                    store = self._store(root, create=False)
                    if store is not None and session.sid in store:
                        del store[session.sid]
                response.delete_cookie(
                    app.config.get('SESSION_COOKIE_NAME', 'session'),
                    domain=domain, path=path,
                )
            gemstone.finalize_flask_request_session()
            return

        with gemstone.session_scope() as s:
            root  = PersistentRoot(s)
            store = self._store(root)
            store[session.sid] = {k: v for k, v in session.items()
                                  if isinstance(v, (str, int, float, bool)) or v is None}

        expires = self.get_expiration_time(app, session)
        response.set_cookie(
            app.config.get('SESSION_COOKIE_NAME', 'session'),
            session.sid,
            expires=expires, httponly=http_only,
            domain=domain, path=path, secure=secure,
        )
        gemstone.finalize_flask_request_session()
