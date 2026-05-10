# Changelog

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
