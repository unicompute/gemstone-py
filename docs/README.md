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
5. [Funny Introduction](funny-introduction/README.md)

If you want a narrative overview before diving in:

- [Medium article](medium-article.md) — a complete end-to-end guide written in article style

If you are already productive and only need answers:

- "Why is my login failing?" → [Setup Guide](setup-guide.md)
- "Which transaction policy should I use?" → [User Manual](user-manual.md)
- "Which example should I run first?" → [Examples Guide](examples-guide.md)
- "How do I do X quickly?" → [Cookbook](cookbook.md)
- "I want the whole story, plus jokes." → [Funny Introduction](funny-introduction/README.md)

## What This Docs Set Covers

- installing and configuring `gemstone-py`
- connecting to a GemStone stone from Python
- transaction policies, session scopes, and failure behaviour
- the persistent data helpers:
  - `PersistentRoot`
  - `GSCollection`
  - `GStore`
  - `ObjectLog`
  - concurrency helpers such as `RCCounter`, `RCHash`, and `RCQueue`
- Flask request-session integration
- benchmarks, release workflows, and the current examples directory

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
