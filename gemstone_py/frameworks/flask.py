"""Flask adapter facade for GemStone request sessions.

The historical import path remains ``gemstone_py.web``. New Flask-specific
code can import this module directly while sharing the same implementation and
backward-compatible objects.
"""

from __future__ import annotations

from gemstone_py.web import (
    close_flask_request_session_provider,
    current_flask_request_session,
    finalize_flask_request_session,
    flask_request_session_provider,
    flask_request_session_provider_metrics,
    flask_request_session_provider_snapshot,
    install_flask_request_session,
    warm_flask_request_session_provider,
)

__all__ = [
    "close_flask_request_session_provider",
    "current_flask_request_session",
    "finalize_flask_request_session",
    "flask_request_session_provider",
    "flask_request_session_provider_metrics",
    "flask_request_session_provider_snapshot",
    "install_flask_request_session",
    "warm_flask_request_session_provider",
]
