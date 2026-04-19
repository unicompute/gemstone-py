"""
Creates a persistent hat (RCQueue) in GemStone and stores it under
PersistentRoot['HatTrickHat'].  Run once to initialise.
"""

PORTING_STATUS = "translated_example"
RUNTIME_REQUIREMENT = "Runs as translated example code on plain GemStone images or standard Python web stacks"

from gemstone_py.example_support import example_session
from gemstone_py.concurrency import RCQueue
from gemstone_py.persistent_root import PersistentRoot

with example_session() as s:
    root = PersistentRoot(s)
    root['HatTrickHat'] = RCQueue(s)   # empty queue — the hat

print('Created empty hat at PersistentRoot[HatTrickHat]')
