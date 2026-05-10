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

## Screenshots

### Example Runner

![gemstone-py Workbench example runner](https://raw.githubusercontent.com/unicompute/gemstone-py/main/vscode-gemstone-py-workbench/media/screenshots/examples-runner.png)

### Environment and Backend Checks

![gemstone-py Workbench environment and backend checks](https://raw.githubusercontent.com/unicompute/gemstone-py/main/vscode-gemstone-py-workbench/media/screenshots/environment-checks.png)

### Database Explorer Launcher

![gemstone-py Workbench database explorer launcher](https://raw.githubusercontent.com/unicompute/gemstone-py/main/vscode-gemstone-py-workbench/media/screenshots/database-explorer.png)

## Development

From this directory:

```bash
npm install
npm run compile
npm run test:smoke
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

The launch command starts the explorer Python executable directly as the VS Code
terminal process. It does not type the command into an interactive shell, which
avoids VS Code Python environment auto-activation interrupting the running Flask
server.

It also opens `http://127.0.0.1:9292/` and can run:

```bash
.venv/bin/python -m pytest -q
npm run test:ui
npm run test:ui:live
```

## Jasper Handoff

Use Jasper for full GemStone/S Smalltalk IDE work. Jasper is the Marketplace
extension `GemTalkSystems.gemstone-ide`:

```bash
code --install-extension GemTalkSystems.gemstone-ide
```

The IDE view's `Open Jasper` and `Use Jasper for Smalltalk IDE work` rows open
Jasper's GemStone sidebar when Jasper is installed. If Jasper is not installed,
they open the VS Code Extensions view filtered to Jasper. The separate `Open
Jasper repository` row opens the Jasper source repository:

https://github.com/jgfoster/Jasper

Use this workbench for Python examples, docs, tests, benchmarks, backend checks,
and launching the Python database explorer:

https://github.com/unicompute/python-gemstone-database-explorer

## Publishing

The repository includes a GitHub Actions workflow named `VS Code Extension`.
It builds a VSIX on extension changes and can publish manually to the Visual
Studio Marketplace.

To enable Marketplace publishing, set a repository secret named `VSCE_PAT` with
a Visual Studio Marketplace personal access token for the `unicompute`
publisher. Then run the workflow with `publish-to-marketplace=true`.

Set `create-github-release=true` on the same manual workflow run when the
Marketplace publish should also create or update the scoped GitHub release tag
`vscode-workbench-v<version>` and attach the packaged VSIX.

Before publishing a new version, the workflow runs release preflight checks for
`package.json`, `package-lock.json`, `CHANGELOG.md`, README screenshot links,
and the packaged VSIX metadata. Keep the Marketplace publisher owner account,
`VSCE_PAT` owner account, and `unicompute.com` domain verification documented in
the publisher admin notes so future releases do not depend on a single browser
session or a stale personal access token.

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## Roadmap

The MVP opens the database explorer in an external browser. A later richer UI
can add a VS Code webview command that embeds a running explorer instance,
checks whether the Flask server is already available, starts it when needed,
and keeps the external-browser command as a fallback.
