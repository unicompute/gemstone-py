"""
User and Tweet domain models backed by GemStone via GSCollection.

Users are stored as dicts in a GSCollection with an equality index on
`@name`, which gives us indexed `find_by_name` queries.

Key difference from the simple_blog example:
  - Uses GSCollection (IdentitySet + equality index) for O(1) user lookup
  - Tweet objects are stored nested inside the User's dict (as JSON)
  - Demonstrates cross-session persistence: signup in one session,
    find_by_name in another
"""

PORTING_STATUS = "translated_example"
RUNTIME_REQUIREMENT = "Runs as translated example code on plain GemStone images or standard Python web stacks"

import json
import time
import uuid

import gemstone_py as gemstone
from gemstone_py.gsquery import GSCollection

USERS_COLLECTION = 'MagTagUsers'
MAX_TIMELINE     = 20     # keep the last 20 timeline events
MAX_TWEET_LENGTH = 140


def _decode_list(value):
    if value is None:
        return []
    if isinstance(value, str):
        if not value:
            return []
        return json.loads(value)
    return list(value)


class UserException(Exception):
    pass


class Tweet:
    """
    A single tweet.  Stored as a nested dict inside the User record.
    """

    def __init__(self, text: str, date: float = None, author: str = ''):
        if len(text) > MAX_TWEET_LENGTH:
            raise ValueError(f"Keep it short, buddy (max {MAX_TWEET_LENGTH} chars)")
        self.text = text
        self.date = date or time.time()
        self.author = author

    def twitterize_date(self, reference: float = None) -> str:
        """Human-readable relative timestamp, port of Tweet#twitterize_date."""
        seconds_ago = int((reference or time.time()) - self.date)
        if seconds_ago < 60:
            return f"{seconds_ago} seconds ago"
        if seconds_ago < 3600:
            return f"{seconds_ago // 60} minutes ago"
        if seconds_ago < 86400:
            return f"{seconds_ago // 3600} hours ago"
        return f"{seconds_ago // 86400} days ago"

    def to_dict(self) -> dict:
        return {'text': self.text, 'date': self.date, 'author': self.author}

    @classmethod
    def from_dict(cls, d: dict) -> 'Tweet':
        return cls(d['text'], d.get('date', time.time()), d.get('author', ''))

    def __repr__(self) -> str:
        return f"Tweet({self.text!r})"


class User:
    """
    A user with followers, following, tweets, and a timeline.

    Backed by GSCollection ('MagTagUsers') with an equality index on
    '@name' for O(log n) find_by_name lookups:

        ALL_USERS = IdentitySet.new
        ALL_USERS.create_equality_index('@name', String)
    """

    _collection: GSCollection | None = None

    # ------------------------------------------------------------------
    # Class-level operations
    # ------------------------------------------------------------------

    @classmethod
    def _col(
        cls,
        session: gemstone.GemStoneSession | None = None,
    ) -> GSCollection:
        """Return the GSCollection, creating and indexing it on first use."""
        if cls._collection is None:
            cls._collection = GSCollection(USERS_COLLECTION)
        col = cls._collection
        # add_index_for_class is idempotent — safe to call each time
        for path in ('@name', '@id'):
            try:
                col.add_index_for_class(path, 'String', session=session)
            except Exception:
                pass
        return col

    @classmethod
    def _rewrite_records(
        cls,
        records: list[dict],
        session: gemstone.GemStoneSession | None = None,
    ) -> None:
        with gemstone.session_scope(session) as s:
            col = cls._col(session=s)
            col.replace_all(records, session=s)
            for path in ('@name', '@id'):
                try:
                    col.add_index_for_class(path, 'String', session=s)
                except Exception:
                    pass

    @classmethod
    def find_by_name(
        cls,
        name: str,
        session: gemstone.GemStoneSession | None = None,
    ) -> 'User | None':
        """
        Find a user by name using the GemStone equality index.

        Returns the User or None if not found.
        """
        with gemstone.session_scope(session) as s:
            col = cls._col(session=s)
            results = col.search('@name', 'eql', name, session=s)
            if not results:
                return None
            return cls._from_record(results[0])

    @classmethod
    def signup(cls, username: str, password: str,
               confirm_pw: str = None,
               session: gemstone.GemStoneSession | None = None) -> 'User':
        """
        Create and persist a new user.

        Raises UserException if:
          - username or password is empty
          - passwords don't match
          - username already taken
        """
        if not username:
            raise UserException("Bad username")
        if not password:
            raise UserException("Bad password")
        if confirm_pw is not None and confirm_pw != password:
            raise UserException("Passwords don't match")
        with gemstone.session_scope(session) as s:
            if cls.find_by_name(username, session=s) is not None:
                raise UserException(f"User {username!r} already taken")

            user = cls(username, password)
            user.save(session=s)
            return user

    @classmethod
    def all(
        cls,
        session: gemstone.GemStoneSession | None = None,
    ) -> list['User']:
        """Return all users as a list."""
        with gemstone.session_scope(session) as s:
            return [cls._from_record(r) for r in cls._col(session=s).all(session=s)]

    @classmethod
    def clear_all(cls, session: gemstone.GemStoneSession | None = None) -> None:
        """Drop and recreate the backing GSCollection for this demo."""
        cls._rewrite_records([], session=session)

    @classmethod
    def _from_record(cls, record: dict) -> 'User':
        u = cls.__new__(cls)
        u.id             = record.get('@id', '')
        u._name          = record.get('@name', '')
        u._password      = record.get('@password', '')
        u._followers     = _decode_list(record.get('@followers', []))
        u._following     = _decode_list(record.get('@following', []))
        u._tweets        = [Tweet.from_dict(d) for d in _decode_list(record.get('@tweets', []))]
        u._timeline      = [Tweet.from_dict(d) for d in _decode_list(record.get('@timeline', []))]
        return u

    # ------------------------------------------------------------------
    # Instance
    # ------------------------------------------------------------------

    def __init__(self, name: str, password: str):
        if not name:
            raise UserException(f"Bad username {name!r}")
        if not password:
            raise UserException("Bad password")
        self.id          = str(uuid.uuid4())
        self._name       = name
        self._password   = password
        self._followers: list[str] = []   # list of usernames
        self._following: list[str] = []   # list of usernames
        self._tweets:    list[Tweet] = []
        self._timeline:  list[Tweet] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def followers(self) -> list[str]:
        return list(self._followers)

    @property
    def following(self) -> list[str]:
        return list(self._following)

    @property
    def tweets(self) -> list[Tweet]:
        return list(self._tweets)

    @property
    def timeline(self) -> list[Tweet]:
        return list(self._timeline)

    def num_followers(self) -> int: return len(self._followers)
    def num_following(self) -> int: return len(self._following)
    def num_tweets(self)   -> int: return len(self._tweets)

    def login(self, password: str) -> bool:
        return password == self._password

    def follow(
        self,
        other: 'User',
        session: gemstone.GemStoneSession | None = None,
    ) -> None:
        """Follow another user; update both sides and persist both."""
        with gemstone.session_scope(session) as s:
            if other.name not in self._following:
                self._following.append(other.name)
            if self._name not in other._followers:
                other._followers.append(self._name)
            self._col(session=s).bulk_upsert_unique(
                '@id',
                [self._to_record(), other._to_record()],
                session=s,
            )

    def add_follower(self, other_name: str) -> None:
        if other_name not in self._followers:
            self._followers.append(other_name)

    def add_timeline(self, tweet: Tweet) -> None:
        self._timeline.append(tweet)
        if len(self._timeline) > MAX_TIMELINE:
            self._timeline = self._timeline[-MAX_TIMELINE:]

    def tweet(
        self,
        text: str,
        session: gemstone.GemStoneSession | None = None,
    ) -> Tweet:
        """
        Create a tweet, prepend to own tweets, push to all followers' timelines.
        """
        with gemstone.session_scope(session) as s:
            new_tweet = Tweet(text, author=self._name)
            self._tweets.insert(0, new_tweet)
            dirty_users = [self]

            # Update each follower's timeline — load, update, save
            for follower_name in self._followers:
                follower = User.find_by_name(follower_name, session=s)
                if follower:
                    follower.add_timeline(new_tweet)
                    dirty_users.append(follower)

            self._col(session=s).bulk_upsert_unique(
                '@id',
                [user._to_record() for user in dirty_users],
                session=s,
            )
            return new_tweet

    def save(self, session: gemstone.GemStoneSession | None = None) -> 'User':
        """Persist this user to GemStone."""
        with gemstone.session_scope(session) as s:
            col = self._col(session=s)
            col.bulk_upsert_unique('@id', [self._to_record()], session=s)
            return self

    def delete(self, session: gemstone.GemStoneSession | None = None) -> None:
        """Remove this user from GemStone."""
        with gemstone.session_scope(session) as s:
            self._col(session=s).bulk_delete_where('@id', [self.id], session=s)

    def _to_record(self) -> dict:
        return {
            '@id':        self.id,
            '@name':      self._name,
            '@password':  self._password,
            '@followers': list(self._followers),
            '@following': list(self._following),
            '@tweets':    [t.to_dict() for t in self._tweets],
            '@timeline':  [t.to_dict() for t in self._timeline[-MAX_TIMELINE:]],
        }

    def __repr__(self) -> str:
        return (f"User({self._name!r}, "
                f"tweets={len(self._tweets)}, "
                f"followers={len(self._followers)})")
