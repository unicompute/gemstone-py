"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");
const vscode = require("vscode");

const extensionId = "unicompute.gemstone-py-workbench";

async function run() {
  const extension = vscode.extensions.getExtension(extensionId);
  assert.ok(extension, `expected ${extensionId} to be installed in the test host`);
  await extension.activate();

  const commands = await vscode.commands.getCommands(true);
  for (const command of [
    "gemstonePy.runFastApiExample",
    "gemstonePy.launchDatabaseExplorer",
    "gemstonePy.configureWorkbench",
    "gemstonePy.openJasper",
  ]) {
    assert.ok(commands.includes(command), `expected command ${command}`);
  }

  const config = vscode.workspace.getConfiguration("gemstonePy");
  const workspacePath =
    process.env.GEMSTONE_PY_INTEGRATION_WORKSPACE || path.dirname(__dirname);
  await config.update("repoPath", workspacePath, vscode.ConfigurationTarget.Workspace);
  await config.update("pythonPath", "python3", vscode.ConfigurationTarget.Workspace);
  await config.update("explorerPath", "", vscode.ConfigurationTarget.Workspace);
  await config.update(
    "env",
    {
      GS_STONE: "gs64stone",
      GS_STONE_NAME: "gs64stone",
      GS_USERNAME: "DataCurator",
      GS_PASSWORD: "",
    },
    vscode.ConfigurationTarget.Workspace,
  );

  const terminalCount = vscode.window.terminals.length;
  await vscode.commands.executeCommand("gemstonePy.runFastApiExample");
  await waitForTerminalCount(terminalCount + 1);
  assert.ok(
    vscode.window.terminals.some(
      (terminal) => terminal.name === "GemStone: FastAPI example",
    ),
    "expected FastAPI example terminal to be opened",
  );

  const explorerTerminalCount = vscode.window.terminals.length;
  const explorerResult = await vscode.commands.executeCommand(
    "gemstonePy.launchDatabaseExplorer",
  );
  assert.equal(explorerResult, false);
  assert.equal(vscode.window.terminals.length, explorerTerminalCount);

  const jasperResult = await vscode.commands.executeCommand("gemstonePy.openJasper");
  assert.match(String(jasperResult), /^(extensions-search|jasper-sidebar)$/);
}

function waitForTerminalCount(expected) {
  return new Promise((resolve, reject) => {
    const started = Date.now();
    const timer = setInterval(() => {
      if (vscode.window.terminals.length >= expected) {
        clearInterval(timer);
        resolve();
      } else if (Date.now() - started > 5000) {
        clearInterval(timer);
        reject(
          new Error(
            `Expected at least ${expected} terminals, saw ${vscode.window.terminals.length}`,
          ),
        );
      }
    }, 50);
  });
}

module.exports = { run };
