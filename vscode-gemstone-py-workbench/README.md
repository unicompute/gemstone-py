# gemstone-py Workbench

<p align="center">
  <img src="https://raw.githubusercontent.com/unicompute/gemstone-py/main/vscode-gemstone-py-workbench/media/emerald-logo.png" alt="gemstone-py Workbench logo" width="96" height="96">
</p>

`gemstone-py Workbench` is a small companion Visual Studio Code extension for
the Python side of GemStone/S work. It complements Jasper instead of replacing
it: Jasper remains the right tool for Smalltalk browser, inspector, debugger,
SUnit, and server-management workflows.

This extension focuses on the `gemstone-py` repository:

- run the maintained Python examples from a sidebar
- pass configured `GS_*` variables into every example terminal
- check the active `gemstone_py._gci` backend
- open the setup, manual, examples, Medium article, and generated PDF docs
- launch a configured `python-gemstone-database-explorer` checkout
- run database explorer tests and UI tests
- run maintainer CI, live, benchmark, and native-check scripts explicitly

## Development

From this directory:

```bash
npm install
npm run compile
```

Open this folder in VS Code and press `F5` to start an extension development
host.

## Install

Install it from the Visual Studio Marketplace:

```bash
code --install-extension unicompute.gemstone-py-workbench
```

Marketplace page:
https://marketplace.visualstudio.com/items?itemName=unicompute.gemstone-py-workbench

## Settings

The extension contributes these settings:

```json
{
  "gemstonePy.pythonPath": "python3",
  "gemstonePy.repoPath": "",
  "gemstonePy.explorerPath": "",
  "gemstonePy.explorerHost": "127.0.0.1",
  "gemstonePy.explorerPort": 9292,
  "gemstonePy.env": {
    "GEMSTONE": "",
    "GS_LIB": "",
    "GS_STONE": "gs64stone",
    "GS_USERNAME": "DataCurator",
    "GS_PASSWORD": "",
    "GS_HOST": "localhost",
    "GS_NETLDI": "netldi",
    "DYLD_LIBRARY_PATH": ""
  }
}
```

Leave `gemstonePy.repoPath` empty when the current VS Code workspace is the
`gemstone-py` checkout. Set `gemstonePy.explorerPath` to a local
`python-gemstone-database-explorer` checkout before using the database explorer
commands.

Set `GS_PASSWORD` locally in your VS Code user settings or workspace settings
before running live examples. The environment view masks password, token,
secret, and key values when it prints a report.

## Example Runner

The Examples view runs these repository modules in a VS Code terminal:

```bash
python3 -m examples.example
python3 -m examples.hello_gemstone
python3 -m examples.misc.smalltalk_demo
python3 -m examples.async_features.session_root_and_collection
python3 -m examples.typed_access.typed_oops_and_queries
python3 -m examples.lifetime.managed_oop_handles
python3 -m examples.native_backend.check_backend
python3 -m uvicorn examples.fastapi.app:app --reload
```

## Database Explorer

The IDE view treats `python-gemstone-database-explorer` as the first-class
Python IDE example app:

```bash
cd /path/to/python-gemstone-database-explorer
python -m gemstone_p.cli --host 127.0.0.1 --port 9292
```

It also opens `http://127.0.0.1:9292/` and can run:

```bash
.venv/bin/python -m pytest -q
npm run test:ui
npm run test:ui:live
```

## Jasper Handoff

Use Jasper for full GemStone/S Smalltalk IDE work:

https://github.com/jgfoster/Jasper

Use this workbench for Python examples, docs, tests, benchmarks, backend checks,
and launching the Python database explorer:

https://github.com/unicompute/python-gemstone-database-explorer
