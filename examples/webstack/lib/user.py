"""
Compatibility wrapper for the translated MagTag user model.

The original `examples/webstack` and the standalone Flask MagTag port are the
same demo expressed through different app layers. Keep them on the
same hardened GSCollection-backed persistence model instead of maintaining two
separate translations with diverging behavior.
"""

from __future__ import annotations

PORTING_STATUS = "application_adaptation"
RUNTIME_REQUIREMENT = "Works on plain GemStone images; uses Flask or Django"

from examples.flask.magtag import models as _shared
Tweet = _shared.Tweet
UserException = _shared.UserException


class User(_shared.User):
    """
    Webstack-facing compatibility shim over the shared GSCollection model.

    The webstack templates expect `num_*` as attributes, while the shared
    model exposes them as methods.  Provide property aliases here so the app
    can stay unchanged while benefitting from the stronger persistence layer.
    """

    @property
    def num_followers(self) -> int:
        return super().num_followers()

    @property
    def num_following(self) -> int:
        return super().num_following()

    @property
    def num_tweets(self) -> int:
        return super().num_tweets()


__all__ = ["Tweet", "User", "UserException"]
