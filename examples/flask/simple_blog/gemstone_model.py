"""
Persistence mixin backed by GemStone, using PersistentRoot and
GciStrKeyValueDictAtPut/GciSymDictAtObjPut directly (no eval).

Each model class stores its instances as a StringKeyValueDictionary
keyed by object id inside PersistentRoot[collection_key].
"""

PORTING_STATUS = "application_adaptation"
RUNTIME_REQUIREMENT = "Works on plain GemStone images; uses Flask or Django"

import time
import uuid

import gemstone_py as gemstone
from gemstone_py.persistent_root import PersistentRoot


def _session(session: gemstone.GemStoneSession | None = None):
    return gemstone.session_scope(session)


class GemStoneModel:
    """
    Minimal persistence mixin backed by GemStone.

    Subclasses must set `collection_key` (str) and implement:
        to_dict()         → dict
        from_dict(data)   → classmethod returning an instance
    """
    collection_key: str = ''

    def __init__(self):
        self.id         = str(uuid.uuid4())
        self.created_at = time.time()

    # ------------------------------------------------------------------
    # Class-level queries
    # ------------------------------------------------------------------

    @classmethod
    def _ensure_collection(cls, root: PersistentRoot):
        key = cls.collection_key
        if key not in root:
            root[key] = {}          # empty StringKeyValueDictionary via dict_to_gs

    @classmethod
    def _collection(cls, root: PersistentRoot):
        cls._ensure_collection(root)
        return root[cls.collection_key]

    @classmethod
    def _record_to_object(cls, record):
        return cls.from_dict({k: record[k] for k in record.keys()})

    @classmethod
    def all(cls, session: gemstone.GemStoneSession | None = None) -> list:
        with _session(session) as s:
            root = PersistentRoot(s)
            col = cls._collection(root)
            return [cls._record_to_object(col[obj_id]) for obj_id in col.keys()]

    @classmethod
    def get(cls, obj_id: str, session: gemstone.GemStoneSession | None = None):
        with _session(session) as s:
            root = PersistentRoot(s)
            col = cls._collection(root)
            if obj_id not in col:
                return None
            return cls._record_to_object(col[obj_id])

    @classmethod
    def get_many(
        cls,
        obj_ids: list[str],
        session: gemstone.GemStoneSession | None = None,
    ) -> list:
        with _session(session) as s:
            root = PersistentRoot(s)
            col = cls._collection(root)
            results = []
            for obj_id in obj_ids:
                if obj_id in col:
                    results.append(cls._record_to_object(col[obj_id]))
            return results

    @classmethod
    def persistent_new(
        cls,
        *args,
        session: gemstone.GemStoneSession | None = None,
        **kwargs,
    ):
        """
        Create, save, and return a new instance in one step.
        """
        instance = cls(*args, **kwargs)
        return cls.stage(instance, session=session)

    @classmethod
    def stage(cls, obj, session: gemstone.GemStoneSession | None = None):
        """
        Stage an object in persistent storage.

        With gemstone-py the session context commits on clean exit, so the
        closest equivalent is saving the record through the current
        persistence layer.
        """
        if not isinstance(obj, cls):
            raise TypeError(f"Cannot stage {type(obj).__name__!r} in {cls.__name__}")
        obj.save(session=session)
        return obj

    @classmethod
    def each(cls, session: gemstone.GemStoneSession | None = None):
        """Yield all persisted instances."""
        yield from cls.all(session=session)

    @classmethod
    def clear_all(cls, session: gemstone.GemStoneSession | None = None):
        """Reset the persisted collection for this model to an empty dict."""
        with _session(session) as s:
            root = PersistentRoot(s)
            root[cls.collection_key] = {}

    # ------------------------------------------------------------------
    # Instance-level persistence
    # ------------------------------------------------------------------

    def save(self, session: gemstone.GemStoneSession | None = None):
        with _session(session) as s:
            root = PersistentRoot(s)
            col = self.__class__._collection(root)
            data    = self.to_dict()
            data['id'] = self.id
            # store record as nested StringKeyValueDictionary
            col[self.id] = data
        return self

    def delete(self, session: gemstone.GemStoneSession | None = None):
        with _session(session) as s:
            root = PersistentRoot(s)
            if self.__class__.collection_key not in root:
                return
            col = root[self.__class__.collection_key]
            del col[self.id]

    # ------------------------------------------------------------------
    # Subclass interface
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        raise NotImplementedError

    @classmethod
    def from_dict(cls, data: dict):
        raise NotImplementedError
