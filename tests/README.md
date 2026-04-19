# Tests

Repository tests live here.

Guidelines:

- keep unit and lightweight integration tests under `tests/`
- use `tests/_support.py` for repo-root path loading in example-app tests
- prefer canonical `gemstone_py` imports in new tests; top-level module imports remain supported for compatibility coverage

Run:

```bash
python3 -m unittest discover -s tests -p 'test*.py'
```

Opt-in live integration coverage:

```bash
GS_RUN_LIVE=1 python3 -m unittest tests.test_live_smoke tests.test_live_integration
```

Destructive live coverage is split behind a second flag. These tests mutate
shared repository state, for example by clearing the ObjectLog:

```bash
GS_RUN_LIVE=1 GS_RUN_DESTRUCTIVE_LIVE=1 python3 -m unittest tests.test_live_integration
```
