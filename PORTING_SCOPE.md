# Porting Scope

`gemstone-py` targets the plain GemStone object model over GCI. Some files
are core runtime code, some are application-level adapters, and some are
example scripts. They are not all the same kind of surface.

## Supported public API

For new code, the supported import path is `gemstone_py.*`.

- canonical runtime/session imports live under `gemstone_py`
- web/session-management helpers live under `gemstone_py.web`
- persistence helpers live under `gemstone_py.persistent_root`,
  `gemstone_py.gstore`, and `gemstone_py.gsquery`
- session-facade helpers live under `gemstone_py.session_facade`

## 1. Plain GemStone Runtime

These work on a normal GemStone image over GCI:

- `gemstone_py.client`
- `gemstone_py.web`
- `gemstone_py.persistent_root`
- `gemstone_py.ordered_collection`
- `gemstone_py.gsquery`
- `gemstone_py.concurrency`
- `gemstone_py.gstore`
- `gemstone_py.objectlog`
- `gemstone_py.smalltalk_bridge`
- `gemstone_py.session_facade`
- most translated persistence, Flask, and Django examples

These modules are realistic ports because they target stable GemStone
facilities: object access, SymbolDictionaries, collections, transactions,
indexes, and ordinary Smalltalk selectors.

## 2. Application Adapters

These are application-level helpers built on top of plain GemStone:

- `examples/flask/simple_blog/gemstone_model.py`
- `examples/flask/sessions/gemstone_sessions.py`
- `examples/flask/transaction_middleware.py`
- `examples/webstack/lib/user.py`

These should be treated as application code, not core runtime.

## 3. Examples

These are runnable demos or sample scripts. They are useful, but they are
not foundational runtime code:

- `example.py`
- `examples/hello_gemstone.py`
- `examples/persistence/...`
- `examples/misc/smalltalk_demo.py`
- `examples/flask/...` app entrypoints
- `examples/webstack/magtag_app.py`

These typically depend on one or more modules from sections 1 and 2.

## 4. Out Of Scope

The following kinds of functionality are out of scope for `gemstone-py`:

- Ruby compiler/runtime classes inside a repository image
- environment-1 method dictionaries and Ruby VM behavior
- image-resident Ruby bridge classes
- Ruby autoload / require / loaded-features bookkeeping

Those areas are outside the scope of this repository. They can only be:

- documented
- wrapped if already present in the target image
- approximated at the API level

They are not part of the supported Python package surface.

## Practical rule

When adding more code to `gemstone-py`:

- if the feature is GemStone object model, selectors, persistence, or transactions, port it
- if the feature is an application helper on top of GemStone, adapt it explicitly
- if the feature depends on a Ruby VM or repository-image Ruby bridge, keep it out of scope and prefer Smalltalk/Python alternatives
