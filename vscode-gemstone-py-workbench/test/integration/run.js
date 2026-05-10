"use strict";

const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { runTests } = require("@vscode/test-electron");

async function main() {
  const extensionDevelopmentPath = path.resolve(__dirname, "..", "..");
  const extensionTestsPath = path.resolve(__dirname, "suite", "index.js");
  const workspacePath = fs.mkdtempSync(
    path.join(os.tmpdir(), "gemstone-py-workbench-"),
  );

  await runTests({
    extensionDevelopmentPath,
    extensionTestsPath,
    launchArgs: [workspacePath, "--disable-workspace-trust"],
    extensionTestsEnv: {
      GEMSTONE_PY_INTEGRATION_WORKSPACE: workspacePath,
    },
  });
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
