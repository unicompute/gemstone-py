# Part VII: Benchmarks, Releases, and Operator Survival

## Opening Thesis

A package becomes mature not when its API looks pretty, but when it can prove
its claims under packaging, release, and operational pressure.

This part is about that proof.

The good news is that `gemstone-py` now has a real story here.

The bad news is that this story involves workflows, baselines, trusted
publishers, runner service management, and PyPI metadata. In other words, it is
the sort of material that turns junior engineers into maintainers.

\newpage

## Benchmarks Are Not Vibes

The package has a maintained benchmark lane. That matters because persistence
helpers do not become good merely by being correct. They also have to avoid
turning ordinary access patterns into performance tax forms.

The benchmark system now includes:

- CLI execution
- JSON artifacts
- report comparison
- baseline manifests
- environment-aware baseline selection
- threshold enforcement in GitHub Actions

That is what it looks like when performance work becomes policy rather than lore.

\newpage

## Smoke Versus Regression

One useful improvement in the benchmark workflow is the split between smoke and
regression profiles.

This is a civilized solution to a common problem.

You often want:

- one cheap signal that the lane still runs at all
- one stricter signal for performance drift

Trying to force one benchmark policy to do both jobs usually produces:

- noisy failures
- unclear expectations
- and arguments about whether the benchmark "really counts"

Named profiles are cleaner.

\newpage

## Baselines Are Managed, Not Worshipped

The package can register benchmark baselines, compare reports against them, and
select environment-matching baselines through a manifest.

That is important because one global baseline file is easy to describe and
almost immediately too naive for reality.

Benchmarks are shaped by:

- runner type
- platform
- Python version
- stone configuration
- workload parameters

The tooling now acknowledges that. Reality is rude, but the tooling no longer
pretends otherwise.

\newpage

## Releases Must Be Proven Twice

One of the package's strongest current features is its release discipline.

The story now includes:

- release dry run
- TestPyPI publish
- PyPI publish
- post-release verification against real PyPI
- installed-artifact contract checks

This is exactly how releases should work:

1. rehearse
2. publish to a rehearsal space
3. publish for real
4. verify the result as a user would see it

That is not overkill. That is the difference between "released" and "uploaded."

\newpage

## Trusted Publishing Was Worth It

The move to trusted publishing means release workflows no longer depend on
long-lived API tokens passed around like cursed treasure.

Instead, the workflow identity itself is part of the release trust model.

That is cleaner and safer.

It is also slightly more bureaucratic the first time you set it up, which is how
you know it is probably doing something useful.

\newpage

## The Post-Release Verify Workflow Is a Love Letter to Reality

The post-release verification workflow does something beautifully simple:

- waits for the version to appear on PyPI
- installs the published artifact
- runs package contract checks
- validates public CLI behaviour
- verifies metadata and long-description hygiene

This closes a painful gap that many packages leave open forever:

> "Yes, we published it. But did the thing the world receives still behave like
> the thing we intended?"

Now the answer can be verified automatically.

\newpage

## The Self-Hosted Runner Story

The live and benchmark workflows depend on a self-hosted runner because the
stone and client library environment are real, stateful, and not meaningfully
reproduced by a generic GitHub-hosted machine.

That means runner operations are part of package quality.

The package now includes:

- bootstrap scripts
- service installation scripts
- launchd integration
- health checks
- upgrade paths
- documentation

This is not glamorous, but it is adult.

\newpage

## A Runner Is Infrastructure, Not a Pet

There is a dangerous tendency to treat one carefully tuned self-hosted runner as
a magical animal that simply exists and should not be questioned.

This is unwise.

A runner should have:

- labels
- a service definition
- update procedures
- health checks
- a failover or recovery story

In short, it should be infrastructure rather than folklore.

\newpage

## Release Notes Matter Too

The package now maintains:

- a changelog
- release metadata checks
- version/tag validation

This sounds bureaucratic until the first moment you need to answer:

> "What changed between 0.2.0 and 0.2.2, and why did we publish 0.2.1 at all?"

At that moment, you either have release discipline or you have interpretive dance.

\newpage

## Public Metadata Is Part of the Product

The work on PyPI long descriptions, project URLs, and metadata hygiene may sound
cosmetic. It is not.

For many users, the PyPI page is the first product surface.

If that page contains:

- broken local absolute paths
- unclear URLs
- stale workflow references

then the package looks unmaintained before the user even installs it.

Metadata is not decoration. It is the front door.

\newpage

## The Release That Taught a Lesson

One useful episode in this package's history involved publishing a correct
release and then noticing that the long description still contained local
absolute paths.

The fix was not dramatic:

- clean the docs source
- cut another release
- verify the public metadata

But the lesson was excellent:

post-release verification is not vanity. It catches what normal build success
cannot see.

\newpage

## A Joke About Maintainers

There comes a point in every package where the maintainer stops saying
"wouldn't it be nice if this worked" and starts saying:

> "What exact workflow, artifact, release, and post-release verification proves
> that it worked?"

That is how maintainers are made.

Somewhere between the first trusted publisher entry and the first benchmark
baseline manifest, a person quietly becomes more responsible than they intended.

\newpage

## The Full Lifecycle, Condensed

Here is the modern package lifecycle in one list:

1. code the change
2. run unit and live checks
3. benchmark if relevant
4. dry-run the release
5. publish to TestPyPI
6. publish to PyPI
7. verify the real release from PyPI
8. keep the runner healthy enough to do it again

That is a proper supply chain story, not a triumphant shell alias.

\newpage

## Final Cartoon-Free Advice

If you maintain this package or one like it:

- prefer boring workflow clarity over cleverness
- write docs for the administrator as well as the user
- keep benchmark policy evidence-based
- verify the thing the outside world actually installs
- treat self-hosted runners like infrastructure

These habits are not glamorous, but they compound into trust.

\newpage

## End of Part VII

You have reached the end of the book.

If you made it this far, you now understand `gemstone-py` from:

- connection setup
- session policy
- persistence design
- query and store helpers
- web integration
- concurrency
- benchmarks
- releases
- operations

That is a substantial amount of ground.

It is also enough ground to be genuinely useful.

\newpage

## Final Notes Page

If you remember only one line from the entire book, make it this one:

> Good persistence software is not just about writing data. It is about making
> the full lifecycle of that data understandable, testable, and survivable.

And if you remember only one joke:

> The stone remembers everything, including your mistakes.

That line has done a remarkable amount of educational work.
