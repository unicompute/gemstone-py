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
  const userDataPath = fs.mkdtempSync(
    path.join(os.tmpdir(), "gemstone-py-workbench-user-data-"),
  );
  const extensionsPath = fs.mkdtempSync(
    path.join(os.tmpdir(), "gemstone-py-workbench-extensions-"),
  );

  await runTests({
    extensionDevelopmentPath,
    extensionTestsPath,
    launchArgs: [
      workspacePath,
      "--disable-workspace-trust",
      `--user-data-dir=${userDataPath}`,
      `--extensions-dir=${extensionsPath}`,
    ],
    extensionTestsEnv: {
      ...process.env,
      GEMSTONE_PY_INTEGRATION_WORKSPACE: workspacePath,
    },
  });
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
