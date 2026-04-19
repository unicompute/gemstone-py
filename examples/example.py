"""
Demonstrates the full gemstone-py API against a live GemStone repository.

Covers:
  - SmalltalkBridge (`smalltalk_bridge.py`)
  - GemStone session facade (`session_facade.py`)
  - PersistentRoot (UserGlobals, Globals, Published, SessionMethods)
  - GStore key/value transactions
  - ObjectLog
  - RCCounter, RCHash, RCQueue
  - Nested transactions + CommitConflictError
  - DateAndTime ↔ datetime
  - Object locking
  - Shared counters
  - listInstances

Run:
    python3 example.py
"""

from datetime import datetime, timezone

import gemstone_py as gemstone
from gemstone_py.concurrency import (
    CommitConflictError,
    RCCounter,
    RCHash,
    RCQueue,
    commit,
    commit_and_release_locks,
    datetime_to_gs,
    gs_datetime,
    gs_now,
    list_instances,
    lock,
    needs_commit,
    nested_transaction,
    read_lock,
    session_count,
    session_id,
    shared_counter_count,
    shared_counter_get,
    shared_counter_increment,
    shared_counter_set,
    transaction_level,
)
from gemstone_py.gstore import GStore
from gemstone_py.objectlog import ObjectLog
from gemstone_py.ordered_collection import OrderedCollection
from gemstone_py.persistent_root import PersistentRoot
from gemstone_py.session_facade import GemStoneSessionFacade
from gemstone_py.smalltalk_bridge import SmalltalkBridge

PORTING_STATUS = "translated_example"
RUNTIME_REQUIREMENT = (
    "Runs as translated example code on plain GemStone images or standard "
    "Python web stacks"
)

SEP = '-' * 56
SESSION_POLICY = gemstone.TransactionPolicy.COMMIT_ON_SUCCESS


def _load_session_config() -> gemstone.GemStoneConfig:
    try:
        return gemstone.GemStoneConfig.from_env()
    except gemstone.GemStoneConfigurationError as exc:
        raise SystemExit(
            f"{exc}\n"
            "Set GS_USERNAME and GS_PASSWORD before running example.py."
        ) from exc


SESSION_CONFIG = _load_session_config()


def _format_mydict(label: str, data) -> str:
    return (
        f"  {label:<13} MyDict       = name={data['name']!r}  "
        f"amount={data['amount']}  currency={data['currency']!r}"
    )


def _inspect_root_dict(root: PersistentRoot, key: str, label: str):
    try:
        value = root[key]
    except KeyError:
        print(f"  {label:<13} {key:<10} = <absent>")
        return None

    if hasattr(value, 'keys'):
        keys = value.keys()
        oop = getattr(value, 'oop', None)
        oop_text = f"0x{oop:X}" if isinstance(oop, int) else 'n/a'
        print(f"  {label:<13} {key:<10} = oop={oop_text} keys={keys}")
        return value

    print(f"  {label:<13} {key:<10} = {value!r}")
    return value


def _print_indented_block(title: str, text: str) -> None:
    print(f"  {title}")
    for line in text.strip().splitlines():
        print(f"    {line}")


PHARO_VERIFY_SNIPPET = """
| session myDict myTestDict |
session := GbsSessionParameters currentSession.
[ session abortTransaction ]
  on: Error
  do: [ session evaluate: 'System abortTransaction. true' ].
myDict := session userGlobals at: #MyDict ifAbsent: [ nil ].
myTestDict := session userGlobals at: #MyTestDict ifAbsent: [ nil ].
Transcript
  show: 'MyDict => '; show: myDict printString; cr;
  show: 'MyDict name => '; show: (myDict at: 'name') printString; cr;
  show: 'MyDict amount => '; show: (myDict at: 'amount') printString; cr;
  show: 'MyDict currency => '; show: (myDict at: 'currency') printString; cr;
  show: 'MyTestDict => '; show: myTestDict printString; cr;
  show: 'MyTestDict name => '; show: (myTestDict at: 'name') printString; cr;
  show: 'MyTestDict keys => '; show: myTestDict keys printString; cr.
"""

# ------------------------------------------------------------------
# GStore — transactional key/value store (own sessions internally)
# ------------------------------------------------------------------
print(SEP)
print('GStore')

db = GStore('example.db', config=SESSION_CONFIG)
with db.transaction() as t:
    t['user:1'] = {'name': 'Alice', 'score': 10}
    t['counter'] = t.get('counter', 0) + 1

with db.transaction(read_only=True) as t:
    print(f"  user:1  = {t['user:1']}")
    print(f"  counter = {t['counter']}")

GStore.rm('example.db')

# ------------------------------------------------------------------
# ObjectLog (own sessions internally)
# ------------------------------------------------------------------
print(SEP)
print('ObjectLog')

log = ObjectLog(config=SESSION_CONFIG)
log.info('example.py started')
log.warn('this is a warning')
log.error('this is an error')

for e in log.infos()[-1:] + log.warns()[-1:] + log.errors()[-1:]:
    print(f"  [{e.level_name:5s}] {e.label!r}")

# ------------------------------------------------------------------
# All single-session operations
# ------------------------------------------------------------------
with gemstone.GemStoneSession(
    config=SESSION_CONFIG,
    transaction_policy=SESSION_POLICY,
) as s:
    st = SmalltalkBridge(s)
    facade = GemStoneSessionFacade(s)

    # ------------------------------------------------------------------
    # SmalltalkBridge
    # ------------------------------------------------------------------
    print(SEP)
    print('SmalltalkBridge')

    repo_name = st.send('SystemRepository', 'name')
    now_via_bridge = st.DateAndTime.now()
    settings = st.StringKeyValueDictionary.new()
    settings['status'] = 'ok'
    print(f"  SystemRepository.name = {repo_name}")
    print(f"  settings['status']    = {settings['status']!r}")
    print(f"  DateAndTime.now.year  = {now_via_bridge.year()}")

    # ------------------------------------------------------------------
    # GemStone session facade
    # ------------------------------------------------------------------
    print(SEP)
    print('GemStone session facade')

    facade['FacadeDemo'] = {'status': 'ready'}
    print(f"  FacadeDemo.status = {facade['FacadeDemo']['status']!r}")
    print(f"  transaction level = {facade.current_transaction_level()}")

    # ------------------------------------------------------------------
    # PersistentRoot — the four SymbolDictionaries
    # ------------------------------------------------------------------
    print(SEP)
    print('PersistentRoot')

    root = PersistentRoot(s)                             # UserGlobals
    globals_        = PersistentRoot.globals(s)          # Globals
    pub             = PersistentRoot.published(s)        # Published
    session_methods = PersistentRoot.session_methods(s)  # SessionMethods
    small_integer   = globals_['SmallInteger']

    _inspect_root_dict(root, 'MyDict', 'before')
    _inspect_root_dict(root, 'MyTestDict', 'before')
    removed_keys = []
    for key in ('MyDict', 'MyTestDict'):
        if key in root:
            del root[key]
            removed_keys.append(key)
    print(f"  cleanup       removed keys = {removed_keys}")
    commit(s)
    print("  cleanup       committed removal pass")
    s.abort()
    root = PersistentRoot(s)
    _inspect_root_dict(root, 'MyDict', 'after cleanup')
    _inspect_root_dict(root, 'MyTestDict', 'after cleanup')
    root['MyDict'] = {'name': 'Tariq', 'amount': 100, 'currency': 'GBP'}
    root['MyTestDict'] = {'name': 'Tariq'}
    d = root['MyDict']
    test_d = root['MyTestDict']
    print(
        f"  UserGlobals  MyDict       = name={d['name']!r}  "
        f"amount={d['amount']}  currency={d['currency']!r}"
    )
    print(f"  UserGlobals  MyDict.keys  = {d.keys()}")
    print(f"  UserGlobals  MyTestDict   = name={test_d['name']!r}")
    print(f"  UserGlobals  MyTestDict.keys = {test_d.keys()}")
    print(f"  UserGlobals  distinct oops = {d.oop != test_d.oop}")
    print(f"  Globals      SmallInteger = {small_integer.name()}")
    print(f"  Globals      superclass   = {small_integer.superclass().name()}")
    print(f"  Globals      sample keys  = {globals_.keys()[:4]}")
    print(f"  Published    keys         = {pub.keys()}")
    print(f"  SessionMethods keys       = {session_methods.keys()}")
    commit(s)
    print("  committed     MyDict and MyTestDict to UserGlobals")
    _print_indented_block('Pharo verify:', PHARO_VERIFY_SNIPPET)
    with gemstone.GemStoneSession(config=SESSION_CONFIG) as s2:
        second_root = PersistentRoot(s2)
        second_d = second_root['MyDict']
        second_test_d = second_root['MyTestDict']
        print(_format_mydict('session 2', second_d))
        print(f"  session 2     MyTestDict.keys = {second_test_d.keys()}")
        print(f"  session 2     distinct oops   = {second_d.oop != second_test_d.oop}")
        print(
            f"  cross-session distinct    = {session_id(s) != session_id(s2)}  "
            f"active sessions = {session_count(s2)}"
        )
    s.abort()
    fresh_root = PersistentRoot(s)
    fresh_d = fresh_root['MyDict']
    fresh_test_d = fresh_root['MyTestDict']
    print(_format_mydict('fresh tx', fresh_d))
    print(f"  fresh tx      MyTestDict.keys = {fresh_test_d.keys()}")
    with gemstone.GemStoneSession(config=SESSION_CONFIG) as session:
        d = PersistentRoot(session)['MyTestDict']
        print(f"  session read   MyTestDict['name'] = {d['name']!r}")
        print(f"  session read   MyTestDict.keys = {d.keys()}")

    # ------------------------------------------------------------------
    # RCCounter
    # ------------------------------------------------------------------
    print(SEP)
    print('RCCounter')

    c = RCCounter(s)
    c.increment()
    c.increment_by(4)
    c.decrement()
    root['hits'] = c
    persisted_hits = root['hits']
    print(f"  value = {persisted_hits.value}")

    # ------------------------------------------------------------------
    # RCHash
    # ------------------------------------------------------------------
    print(SEP)
    print('RCHash')

    h = RCHash(s)
    h['session:1'] = 'active'
    h['session:2'] = 'idle'
    del h['session:2']
    root['sessions'] = h
    persisted_sessions = root['sessions']
    print(f"  session:1 = {persisted_sessions['session:1']!r}  size = {persisted_sessions.size}")
    print(f"  keys      = {persisted_sessions.keys()}")

    # ------------------------------------------------------------------
    # RCQueue
    # ------------------------------------------------------------------
    print(SEP)
    print('RCQueue')

    q = RCQueue(s)
    q.push('job-1')
    q.push('job-2')
    q.push('job-3')
    root['jobs'] = q
    persisted_jobs = root['jobs']
    print(f"  first = {persisted_jobs.first!r}  size = {persisted_jobs.size}")
    print(f"  pop   = {persisted_jobs.pop()!r}  size = {persisted_jobs.size}")

    # ------------------------------------------------------------------
    # Nested transactions
    # ------------------------------------------------------------------
    print(SEP)
    print('Nested transactions')

    with nested_transaction(s):
        root['draft'] = {'status': 'pending', 'ref': 'NTX-001'}
    print(f"  draft.status = {root['draft']['status']!r}")

    # ------------------------------------------------------------------
    # CommitConflictError
    # ------------------------------------------------------------------
    print(SEP)
    print('commit() with conflict detection')

    try:
        commit(s)
        print('  commit: OK')
    except CommitConflictError as e:
        print(f"  conflict: {e.report}")

    # ------------------------------------------------------------------
    # DateAndTime ↔ datetime
    # ------------------------------------------------------------------
    print(SEP)
    print('DateAndTime')

    now    = gs_now(s)
    dt_oop = datetime_to_gs(s, datetime.now(timezone.utc))
    back   = gs_datetime(s, dt_oop)
    print(f"  bridge year        = {now_via_bridge.year()}")
    print(f"  gs_now()          = {now.isoformat()}")
    print(f"  roundtrip delta   < 2s: {abs((back - now).total_seconds()) < 2}")

    # ------------------------------------------------------------------
    # Object locking
    # ------------------------------------------------------------------
    print(SEP)
    print('Object locking')

    lock_target = st.Object.new()
    with lock(s, lock_target):
        print('  write lock acquired and released')
    with read_lock(s, lock_target):
        print('  read lock acquired and released')

    # ------------------------------------------------------------------
    # Shared counters
    # ------------------------------------------------------------------
    print(SEP)
    print('Shared counters')

    shared_counter_set(s, 1, 0)
    shared_counter_increment(s, 1)
    shared_counter_increment(s, 1, by=4)
    print(f"  counter[1]       = {shared_counter_get(s, 1)}")
    print(f"  total counters   = {shared_counter_count(s)}")

    # ------------------------------------------------------------------
    # OrderedCollection
    # ------------------------------------------------------------------
    print(SEP)
    print('OrderedCollection')

    col = OrderedCollection(s)
    col.append('alpha')
    col.append('beta')
    col.append('gamma')
    root['ordered'] = col
    persisted_col = root['ordered']
    print(
        f"  col[0]  = {persisted_col[0]!r}  "
        f"last = {persisted_col.last!r}  len = {len(persisted_col)}"
    )
    print(f"  size()  = {persisted_col.size()}  at_(1) = {persisted_col.at_(1)!r}")
    persisted_col.delete('beta')
    print(f"  after delete('beta'): {persisted_col.to_list()}")

    # ------------------------------------------------------------------
    # Session utilities
    # ------------------------------------------------------------------
    print(SEP)
    print('Session utilities')

    print(f"  session_id      = {session_id(s)}")
    print(f"  session_count   = {session_count(s)}")
    print(f"  transaction_level           = {transaction_level(s)}")
    print(f"  needs_commit (before)       = {needs_commit(s)}")
    root['probe'] = 'dirty'
    print(f"  needs_commit (after write)  = {needs_commit(s)}")
    commit_and_release_locks(s)
    print(f"  needs_commit (after c&rl)   = {needs_commit(s)}")

    # ------------------------------------------------------------------
    # listInstances
    # ------------------------------------------------------------------
    print(SEP)
    print('listInstances')

    rc_inst = RCCounter(s)
    rc_inst.increment_by(7)
    root['rc_inst'] = rc_inst
    commit(s)
    instances = list_instances(s, 'RcCounter', wrap=True)
    current = next((inst for inst in instances if inst.oop == rc_inst.oop), None)
    print(f"  RcCounter instances in repository: {len(instances)}")
    print(
        "  current rc_inst listed = "
        f"{current is not None}  value = {current.value if current else 'n/a'}"
    )

    print(SEP)
    # session commits on clean __exit__
