# Miscellaneous Examples

Smalltalk-first helper examples for `gemstone-py`.

## WebTools

There is no local Python port of the old WebTools demo in this repository.

## smalltalk_demo.py

Demonstrates the default Python-to-Smalltalk path:

- `SmalltalkBridge` for resolving Smalltalk globals and sending selectors
- `GemStoneSessionFacade` for a compact persistent-root and transaction API
- plain Python values being marshalled through the Smalltalk bridge

Run:

```bash
python3 -m examples.misc.smalltalk_demo
gemstone-smalltalk-demo
```

This is the recommended path on plain GemStone.

For the broader classification, see
[PORTING_SCOPE.md](/Users/tariq/src/gemstone-py/PORTING_SCOPE.md).

Related files:

- [smalltalk_demo.py](/Users/tariq/src/gemstone-py/examples/misc/smalltalk_demo.py)
