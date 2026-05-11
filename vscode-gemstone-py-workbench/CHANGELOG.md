# Changelog

## 0.2.1

- Added Workbench commands and Examples view rows for the new example catalog,
  quickstart, Litestar runner, and Plan3 feature map examples.
- Added Docs view shortcuts for the Plan3 feature map and framework-adapter
  documentation, including generated PDFs.

## 0.2.0

- Added `gemstone-py: Open Database Explorer in VS Code`, which embeds the
  configured database explorer URL in a VS Code webview while keeping the
  external browser command available.
- Added action buttons to `gemstone-py: Verify Workbench Setup` for opening
  settings, copying the report, and copying the environment export script.
- Added Jasper handoff status to the setup verification report.
- Added live extension-host CI coverage that can assert the setup verifier
  reaches a real GemStone stone and returns `7`.
- Added full release verification automation and Marketplace publisher-domain
  checks.
- Added a Marketplace/GitHub workflow screenshot for configure, verify, and
  embedded explorer usage.

## 0.1.11

- Added `gemstone-py: Configure Workbench`, a first-run setup command for
  Python, checkout, database explorer, and GemStone connection settings.
- Added `gemstone-py: Verify Workbench Setup`, which reports Python path,
  checkout, explorer, credential, stone alias, GCI library, native backend, and
  optional live GemStone connectivity status in one output report.
- Added VS Code extension-host integration smoke tests with
  `@vscode/test-electron`.
- Added VSIX checksum generation for GitHub release assets.

## 0.1.10

- Added a pre-launch settings check for the database explorer so missing
  `GS_USERNAME` or `GS_PASSWORD` is reported as a workbench warning.
- Updated the Marketplace workflow to verify the public listing after publish.

## 0.1.9

- Updated Marketplace screenshots for the examples runner, environment/backend checks, and database explorer launcher.

## 0.1.8

- Prefer `.venv/bin/python` from the configured `gemstone-py` checkout when `gemstonePy.pythonPath` is empty, so example commands use the repository virtualenv by default.
- Updated setup docs to leave `gemstonePy.pythonPath` empty for automatic virtualenv detection.

## 0.1.7

- Changed the FastAPI example command to run `python -m examples.fastapi.run --reload`, which checks for missing FastAPI/uvicorn dependencies and prints the correct install command before starting uvicorn.

## 0.1.6

- Changed the Jasper IDE handoff to open the installed `GemTalkSystems.gemstone-ide` extension's GemStone sidebar instead of opening GitHub.
- Open the VS Code Extensions view filtered to Jasper when Jasper is not installed.
- Added a separate Jasper repository link and smoke coverage for the installed, missing, and repository paths.

## 0.1.5

- Made the "Use Jasper for Smalltalk IDE work" IDE tree row open Jasper instead of acting as inert descriptive text.
- Added smoke coverage so both Jasper rows remain wired to the Jasper command.

## 0.1.4

- Changed the database explorer launcher to start the explorer Python process directly in the VS Code terminal instead of typing a shell command with `sendText`.
- Avoided races with VS Code Python terminal auto-activation that could inject `source .venv/bin/activate` and interrupt the running Flask server.
- Added smoke coverage for the direct launcher behavior.

## 0.1.3

- Added Marketplace screenshot assets for the examples runner, environment/backend checks, and database explorer launcher.
- Added screenshot links to the extension README using raw GitHub URLs so the Visual Studio Marketplace can render them reliably.
- Kept the embedded database explorer webview as a documented future feature instead of adding it to the MVP.

## 0.1.2

- Bumped the extension package after adding the automated VSIX build and manual Marketplace publish workflow.
- Documented Marketplace publishing with `VSCE_PAT`.
- Added a roadmap note for a later embedded database explorer webview.

## 0.1.1

- Updated the README logo to use an HTTPS raw GitHub image URL for Marketplace rendering.

## 0.1.0

- Initial gemstone-py Workbench MVP.
- Added examples, environment, docs, maintainer, and IDE sidebar views.
- Added commands for running examples, checking the backend, opening docs, launching the database explorer, and handing off to Jasper.
