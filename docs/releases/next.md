# gemstone-py Next Release Draft

This draft covers the post-0.2.10 work from the plan3 implementation pass. Use
it as the starting point for the next GitHub release notes after choosing the
final version number.

## Suggested Version

Use a patch release if you are only publishing the current docs, examples, and
adapter additions:

```bash
0.2.11
```

Use a minor release if you want to present the web-adapter split as a larger
feature milestone:

```bash
0.3.0
```

## Highlights

- Added production session provider internals under
  `gemstone_py.session_providers` while keeping historical `gemstone_py.web`
  imports and top-level exports stable.
- Added a dependency-light Django adapter in `gemstone_py.frameworks.django`.
- Added a Litestar adapter example and packaged runner:
  `gemstone-litestar-example`.
- Added `examples/litestar/` and `examples/cookbook/` so new users can find
  the async web and cookbook paths quickly.
- Added `gemstone-examples list` and `gemstone-examples litestar`.
- Added `docs/framework-adapters.md` with the sync and async adapter recipe.
- Reworked the README first screen around a two-minute start path and clearer
  production/cookbook links.
- Regenerated the documentation PDFs to include the new adapter and examples
  material.

## Install

```bash
python -m pip install gemstone-py
python -m pip install "gemstone-py[fast]"
```

For web examples:

```bash
python -m pip install "gemstone-py[fastapi]"
gemstone-fastapi-example --reload

python -m pip install "gemstone-py[litestar]"
gemstone-litestar-example --reload

python -m pip install "gemstone-py[django]"
```

For a source checkout:

```bash
python -m pip install -e ".[examples]"
gemstone-examples list
python -m examples.quickstart
python -m examples.fastapi.run --reload
python -m examples.litestar.run --reload
```

## Verify Before Release

Run the local checks:

```bash
.venv/bin/python -m ruff check gemstone_py tests
.venv/bin/python -m mypy
.venv/bin/python -m pytest -q
.venv/bin/python -m gemstone_py.api_contract --json
GS_SKIP_BUILD_SMOKE=1 ./scripts/run_ci_checks.sh
```

Run the full release wrapper when public artifacts are expected to exist:

```bash
./scripts/release_all.sh
```

## Draft GitHub Release Body

````markdown
## Highlights

- Added framework-neutral web lifecycle docs and examples for Flask, Django,
  FastAPI, and Litestar.
- Added `gemstone_py.session_providers` as the canonical home for reusable sync
  session pools/providers while preserving old imports.
- Added `gemstone-litestar-example`, `examples/litestar/`,
  `gemstone-examples litestar`, and `gemstone-examples list`.
- Added `examples/cookbook/` as the stable table of contents for example
  selection.
- Polished the README around a two-minute start path.

## Install

```bash
python -m pip install gemstone-py
python -m pip install "gemstone-py[fast]"
```

## Verify

```bash
gemstone-examples list
gemstone-examples quickstart
gemstone-fastapi-example --reload
gemstone-litestar-example --reload
```
````
