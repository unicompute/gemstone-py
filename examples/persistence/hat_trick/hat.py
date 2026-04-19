"""
Port of hat.rb — the Hat class.

A container for Rabbits and other magician's props.
"""

PORTING_STATUS = "translated_example"
RUNTIME_REQUIREMENT = "Runs as translated example code on plain GemStone images or standard Python web stacks"


class Hat:
    def __init__(self):
        self._contents = []

    def put(self, item):
        self._contents.append(item)

    @property
    def contents(self):
        return self._contents

    def __len__(self):
        return len(self._contents)

    def __repr__(self):
        return f"Hat({self._contents!r})"
