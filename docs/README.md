# gemstone-py Documentation

This directory contains the longer-form documentation set for `gemstone-py`.
The top-level `README.md` in the repo is still the quickest way to get the
package installed, but the files here are meant to answer the questions people
ask on day two, day ten, and day forty-five.

## Reading Order

If you are new to the project, use this order:

1. [Setup Guide](setup-guide.md)
2. [User Manual](user-manual.md)
3. [Examples Guide](examples-guide.md)
4. [Cookbook](cookbook.md)
5. [Plan3 Feature Map](plan3-feature-map.md)
6. [Type-Safe Smalltalk Codegen](codegen.md)
7. [Framework Adapters](framework-adapters.md)
8. [Observability](observability.md)
9. [Performance](performance.md)
10. [Rust Client](rust-client.md)
11. [Funny Introduction](funny-introduction/README.md)

If you want a narrative overview before diving in:

- [Medium article](medium-article.md) — a complete end-to-end guide written in article style

For release preparation:

- [Next release draft](releases/next.md)

If you are already productive and only need answers:

- "Why is my login failing?" → [Setup Guide](setup-guide.md)
- "Which transaction policy should I use?" → [User Manual](user-manual.md)
- "Which example should I run first?" → [Examples Guide](examples-guide.md)
- "Which plan3 stream maps to which code?" → [Plan3 Feature Map](plan3-feature-map.md)
- "How do I do X quickly?" → [Cookbook](cookbook.md)
- "How do I generate typed wrappers from Protocols?" → [Type-Safe Smalltalk Codegen](codegen.md)
- "How do I reduce round trips without adding an ORM?" → [User Manual](user-manual.md)
- "How do I retry commit conflicts deliberately?" → [Cookbook](cookbook.md)
- "How do I add another web framework?" → [Framework Adapters](framework-adapters.md)
- "How do I trace or measure GemStone calls?" → [Observability](observability.md)
- "Can a Rust application talk to GemStone directly?" → [Rust Client](rust-client.md)
- "How do I inspect an OOP or class?" → [User Manual](user-manual.md)
- "What are the current benchmark numbers?" → [Performance](performance.md)
- "I want the whole story, plus jokes." → [Funny Introduction](funny-introduction/README.md)
- "Can I run these from VS Code?" → [`vscode-gemstone-py-workbench`](../vscode-gemstone-py-workbench/)

## What This Docs Set Covers

- installing and configuring `gemstone-py`
- connecting to a GemStone stone from Python
- GemStone-side bootstrap for the shared helper roots
- transaction policies, session scopes, and failure behaviour
- async sessions and FastAPI/Litestar request integration
- typed OOPs, typed `GSCollection` queries, and managed OOP lifetimes
- Protocol-to-Smalltalk code generation with checked-in typed wrappers
- generated wrapper metadata, `.pyi` stubs, async wrappers, and CI drift checks
- bulk selector sends, persistent-root batch reads/writes, and collection batch updates
- explicit transaction retry helpers and user-facing conflict diagnostics
- opt-in scalar value converters for `datetime`, `date`, `Decimal`, `UUID`, and dataclass payloads
- schema fingerprinting for expected roots, GemStone classes, and migration state
- OOP/class inspection and recursive debug dumps
- optional native PyO3 backend installation and backend selection
- a direct Rust client foundation in the separate `gemstone-rs` workspace
- the persistent data helpers:
  - `PersistentRoot`
  - `GSCollection`
  - `GStore`
  - `ObjectLog`
  - concurrency helpers such as `RCCounter`, `RCHash`, and `RCQueue`
- Flask, Django, FastAPI, and Litestar request-session integration
- tracing, metrics, and slow-operation logs for session calls
- benchmark numbers, release workflows, and the current examples directory
- a plan3 feature map that links major features to modules, examples, and docs
- the companion VS Code workbench for running examples, opening docs, checking
  backends, launching the Python database explorer, and handing Smalltalk IDE
  work to Jasper

## Current Lightweight Improvements

The recent improvements deliberately keep `gemstone-py` as a thin GemStone
client rather than an object mapper. The main additions are explicit helpers
that reduce repeated boilerplate or repeated round trips:

- `PersistentRoot.get_many(...)`, `PersistentRoot.update_many(...)`,
  `GsDict.get_many(...)`, and `GsDict.update_many(...)` for batch dictionary
  access.
- `GemStoneSession.bulk_perform_*`, `perform_many_*`, and `PerformCall` for
  sending one or more selectors across raw OOPs in one evaluated batch.
- `run_transaction_with_retry(...)` and `retrying_transaction(...)` for bounded
  replay of a whole unit of work after `CommitConflictError`.
- `format_commit_conflict(...)` and structured conflict diagnostics for logs,
  CLI output, and incident reports.
- `scalar_value_converter_registry()` and `dataclass_to_dict(...)` for explicit
  value conversion when a GemStone API expects scalar OOP arguments or plain
  mapping payloads.
- `schema_fingerprint(...)`, `assert_schema_fingerprint(...)`, and
  `gemstone-migrations fingerprint` for deployment-time checks that a stone has
  the expected roots, classes, and migration state.

These are intentionally not a hidden identity map. If an application wants a
domain model, it can build one on top of these primitives without the client
guessing object identity, lifetime, or persistence semantics behind its back.

## Visuals

The images under `docs/assets/` are intentionally repository-native SVG files.
That gives you a few benefits:

- they render nicely on GitHub
- they can be edited in a normal text diff
- they do not bloat the repository with binary noise
- they can be reused in presentations, blog posts, or generated manuals

Some of the "screenshots" are stylized screenshot illustrations rather than raw
captures. That is deliberate: the examples evolve, and the docs should remain
easy to maintain.

## Print-Friendly Book

The long-form introduction under [`funny-introduction/`](funny-introduction/README.md)
is structured as a book, with explicit page breaks for a print/export workflow.
It is designed to compile to more than one hundred pages when rendered to PDF or
another paged format.

## Suggested Build / Export Flow

If you want to turn these docs into a PDF bundle later, a practical approach is:

1. keep the Markdown source here as the canonical text
2. render the long introduction as a separate book
3. render the setup guide, manual, examples guide, and cookbook as a smaller companion manual

That split keeps the funny book delightfully excessive and the operational docs
pleasantly searchable.
