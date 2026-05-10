"""Demonstrate managed and explicitly scoped GemStone OOP handles.

This module expects the usual GemStone environment variables. Run it from the
repository root with:

    python -m examples.lifetime.managed_oop_handles
"""

from __future__ import annotations

from gemstone_py.example_support import MANUAL_POLICY, example_session


def main() -> None:
    with example_session(transaction_policy=MANUAL_POLICY) as session:
        collection = session.execute_managed("OrderedCollection new")
        try:
            collection.send("add:", session.new_string("managed"))
            print(f"managed handle keeps object alive: {collection.print_string()}")

            session.eval("System startGcAndCommit")
            print(f"after GemStone GC: {collection.print_string()}")

            raw_oop = session.execute_oop("OrderedCollection new")
            with session.handle(raw_oop) as handle:
                handle.send("add:", session.new_string("scoped"))
                print(f"scoped handle: {handle.send('printString')}")

            session.abort()
        finally:
            collection.close()


if __name__ == "__main__":
    main()
