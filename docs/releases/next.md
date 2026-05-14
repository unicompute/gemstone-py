# gemstone-py Next Release Draft

This draft is for work after `0.2.14`. Keep it aligned with the Unreleased
section in `CHANGELOG.md` until the final release version is chosen.

## Suggested Version

Use a patch release for small follow-up fixes:

```bash
0.2.15
```

Use a minor release for the next larger feature milestone:

```bash
0.3.2
```

## Highlights

- Lightweight bulk operations for mixed selector sends and persistent-root
  batch get/update workflows.
- Explicit transaction retry helpers plus clearer conflict diagnostics and
  bounded inspection output.
- Opt-in value converters for scalar-ish Python values, including the installed
  `gemstone-examples value-converters` preview.
- Schema fingerprinting helpers for startup checks around roots, class
  definitions, and indexes.
- Generated wrapper metadata through `__gemstone_protocol__` and
  `__gemstone_selectors__` for diagnostics and tooling.

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
gemstone-examples plan3-map
gemstone-examples value-converters
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
./scripts/check_codegen.sh
GS_SKIP_BUILD_SMOKE=1 ./scripts/run_ci_checks.sh
```

Run the full release wrapper when public artifacts are expected to exist:

```bash
./scripts/release_all.sh
```

## Draft GitHub Release Body

````markdown
## Highlights

- Lightweight bulk operations reduce round trips for common object and root
  access patterns.
- Explicit retry, conflict diagnostics, inspection limits, value converters,
  schema fingerprinting, and generated-wrapper metadata improve day-to-day
  ergonomics without adding object mapping or a hidden identity map.

## Install

```bash
python -m pip install gemstone-py
python -m pip install "gemstone-py[fast]"
```

## Verify

```bash
gemstone-examples list
gemstone-examples value-converters
gemstone-codegen \
  --module examples.typed_access.codegen_demo.models \
  --output examples/typed_access/codegen_demo/generated \
  --check
```
````
