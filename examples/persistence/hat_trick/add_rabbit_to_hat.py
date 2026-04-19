"""
Adds a Rabbit to the persistent hat each time it's run.
"""

PORTING_STATUS = "translated_example"
RUNTIME_REQUIREMENT = "Runs as translated example code on plain GemStone images or standard Python web stacks"

from gemstone_py.example_support import example_session
from gemstone_py.persistent_root import PersistentRoot

RABBIT = r"""
 () ()
( '.' )
(")_(")
"""

with example_session() as s:
    root = PersistentRoot(s)
    hat  = root['HatTrickHat']          # GsDict wrapping the live RCQueue OOP
    hat._call('add:', RABBIT)           # push via the proxy's underlying perform
    size = hat._call('size')

print(f'Added a rabbit. Hat now contains {size} rabbit(s).')
