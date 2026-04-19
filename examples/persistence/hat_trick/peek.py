"""
PersistentRoot "peek" helper.

This example stores a callable Smalltalk snippet in UserGlobals so that any
Python session can inspect committed PersistentRoot state:

    peek('HatTrickHat')     # => the Hat object

GemStone closures that capture no variables can be persisted as compiled
method blocks, but for simplicity this port stores the block *source string*
as a String in UserGlobals under the key 'peek', plus a pure-Python helper
function `peek()` with identical semantics.

Usage
-----
First run this script to persist the Smalltalk block source string:

    python3 peek.py

Then from any Python session use the helper:

    from peek import peek
    obj = peek('HatTrickHat')     # returns GsDict proxy or prints all keys

Or evaluate the stored Smalltalk snippet via eval:

    from peek import peek_smalltalk
    print(peek_smalltalk('HatTrickHat'))
"""

PORTING_STATUS = "translated_example"
RUNTIME_REQUIREMENT = "Runs as translated example code on plain GemStone images or standard Python web stacks"

import sys

from gemstone_py.example_support import READ_POLICY, example_session
from gemstone_py.persistent_root import PersistentRoot

# ---------------------------------------------------------------------------
# The Smalltalk block source stored as the "callable" in UserGlobals.
# In GemStone this is a String; you can eval it, passing any key name.
# ---------------------------------------------------------------------------

_PEEK_BLOCK_SOURCE = (
    "[:obj | "
    "  | root |\n"
    "  System abortTransaction.\n"
    "  root := UserGlobals.\n"
    "  (root includesKey: obj asSymbol)\n"
    "    ifTrue:  [ (root at: obj asSymbol) printString ]\n"
    "    ifFalse: [ root keys printString ]\n"
    "]"
)


def _store_peek_block() -> None:
    """Persist the peek block source string in UserGlobals at key #peek."""
    with example_session() as s:
        s.eval(
            f"UserGlobals at: #peek put: '{_PEEK_BLOCK_SOURCE.replace(chr(39), chr(39)*2)}'."
        )
    print("Stored peek block source at UserGlobals[#peek]")


# ---------------------------------------------------------------------------
# Python-side helper with the same semantics as the stored block
# ---------------------------------------------------------------------------

def peek(key: str):
    """
    Spy on a PersistentRoot entry, aborting first so we see committed state.

    Parameters
    ----------
    key : str
        The PersistentRoot key to inspect (e.g. 'HatTrickHat').

    Returns
    -------
    object
        The most natural Python-side proxy for the entry if it exists
        (for example `RCQueue`, `RCCounter`, `OrderedCollection`, `GsDict`,
        or a plain list), or a list of all PersistentRoot keys when the key
        is not found.

    Example
    -------
        from peek import peek
        hat = peek('HatTrickHat')
        print(hat)
    """
    with example_session(transaction_policy=READ_POLICY) as s:
        s.abort()                           # see committed state before reading
        root = PersistentRoot(s)
        if key in root:
            return root[key]
        return root.keys()


def peek_smalltalk(key: str) -> str:
    """
    Run the stored Smalltalk peek block against `key` and return the
    printString result.

    This evaluates the block persisted by _store_peek_block() directly inside
    GemStone.

    Parameters
    ----------
    key : str
        A string that will be passed as the block argument (coerced to Symbol
        inside Smalltalk via asSymbol).

    Returns
    -------
    str
        The printString result from GemStone.
    """
    with example_session(transaction_policy=READ_POLICY) as s:
        raw = s.eval(
            f"| blkSrc |\n"
            f"blkSrc := UserGlobals at: #peek ifAbsent: [''].\n"
            f"blkSrc isEmpty\n"
            f"  ifTrue:  ['peek block not stored — run peek.py first']\n"
            f"  ifFalse: [ (Compiler evaluate: blkSrc) value: '{key}' ]"
        )
        return str(raw)


# ---------------------------------------------------------------------------
# Main — store the block when run directly
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    _store_peek_block()

    # Demonstrate the Python-side helper
    key = sys.argv[1] if len(sys.argv) > 1 else 'HatTrickHat'
    print(f"\npeek({key!r}):")
    result = peek(key)
    print(f"  {result!r}")

    # Demonstrate the Smalltalk-side helper
    print(f"\npeek_smalltalk({key!r}):")
    print(f"  {peek_smalltalk(key)}")
