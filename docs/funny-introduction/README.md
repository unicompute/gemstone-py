# A Funny but Thorough Introduction to gemstone-py

Welcome to the long-form book.

This is the version of the documentation for people who want:

- an honest explanation of how `gemstone-py` works
- enough jokes to stay awake
- diagrams, cartoons, and screenshot-style illustrations
- something you can realistically export as a 100+ page PDF and hand to a new teammate

## Structure

The book is split into seven parts:

1. [Part I: Why gemstone-py Exists](part-01-why-gemstone-py-exists.md)
2. [Part II: Sessions and Transactions](part-02-sessions-and-transactions.md)
3. [Part III: PersistentRoot and Friends](part-03-persistent-root-and-friends.md)
4. [Part IV: Queries, Stores, and Logs](part-04-queries-stores-and-logs.md)
5. [Part V: Web Apps and Request Lifecycles](part-05-web-apps-and-request-lifecycles.md)
6. [Part VI: Concurrency, Conflicts, and Retries](part-06-concurrency-conflicts-and-retries.md)
7. [Part VII: Benchmarks, Releases, and Operator Survival](part-07-benchmarks-releases-and-operator-survival.md)

## Page Count

Each part is formatted with explicit page breaks (`\newpage`) and enough section
structure to render as a paged manual. The full set is designed to exceed one
hundred pages when exported to PDF or another paged format.

That sounds excessive because it is excessive.

It is also surprisingly useful when you need a document that can serve as:

- onboarding guide
- technical narrative
- architectural explanation
- examples companion
- occasional morale support device

## Tone

This book follows a simple rule:

> If a topic is important, explain it clearly. If it is dangerous, explain it
> clearly and make the joke sharper.

That means:

- transaction policy sections are serious
- commit conflict sections are serious but slightly theatrical
- queue jokes are regrettably inevitable

## Suggested Reading Paths

### New user

Read Parts I, II, and III first.

### Web-focused user

Read Parts I, II, and V first.

### Operations-focused user

Read Parts II, VI, and VII first.

### Person who enjoys complete narratives

Read the whole thing in order and accept that you are now the office historian.
