"""
Prints the contents of the persistent hat.
"""

PORTING_STATUS = "translated_example"
RUNTIME_REQUIREMENT = "Runs as translated example code on plain GemStone images or standard Python web stacks"

from gemstone_py.example_support import READ_POLICY, example_session
from gemstone_py.concurrency import RCQueue
from gemstone_py.persistent_root import PersistentRoot

with example_session(transaction_policy=READ_POLICY) as s:
    root = PersistentRoot(s)
    hat  = root['HatTrickHat']
    if not isinstance(hat, RCQueue):
        raise TypeError(
            f"Expected PersistentRoot['HatTrickHat'] to be an RCQueue, got {type(hat).__name__}"
        )
    size = hat.size
    print(f'The hat contains {size} rabbit(s)')
    for item in hat:
        print(item)
