# gemstone-py Next Release Draft

This draft is for work after `0.2.11`. Move concrete entries here as the next
release starts to take shape.

## Suggested Version

Use a patch release for small follow-up fixes:

```bash
0.2.12
```

Use a minor release for the next larger feature milestone:

```bash
0.3.0
```

## Highlights

- Pending.

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

- Pending.

## Install

```bash
python -m pip install gemstone-py
python -m pip install "gemstone-py[fast]"
```

## Verify

```bash
gemstone-examples list
```
````
