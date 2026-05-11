#!/usr/bin/env node
"use strict";

const childProcess = require("child_process");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");

function readJson(relativePath) {
  return JSON.parse(fs.readFileSync(path.join(root, relativePath), "utf8"));
}

function fail(message) {
  console.error(`release preflight failed: ${message}`);
  process.exitCode = 1;
}

function assert(condition, message) {
  if (!condition) {
    fail(message);
  }
}

function findVsixFiles() {
  return fs
    .readdirSync(root)
    .filter((name) => name.endsWith(".vsix"))
    .sort();
}

function readVsixPackageJson(vsixName) {
  const vsixPath = path.join(root, vsixName);
  try {
    const output = childProcess.execFileSync(
      "unzip",
      ["-p", vsixPath, "extension/package.json"],
      { encoding: "utf8" },
    );
    return JSON.parse(output);
  } catch (error) {
    fail(`could not read extension/package.json from ${vsixName}: ${error.message}`);
    return {};
  }
}

const packageJson = readJson("package.json");
const packageLock = readJson("package-lock.json");
const changelog = fs.readFileSync(path.join(root, "CHANGELOG.md"), "utf8");
const readme = fs.readFileSync(path.join(root, "README.md"), "utf8");
const version = packageJson.version;
const packageName = packageJson.name;

assert(version, "package.json must include version");
assert(
  packageLock.version === version,
  `package-lock.json version ${packageLock.version} does not match package.json ${version}`,
);
assert(
  packageLock.packages &&
    packageLock.packages[""] &&
    packageLock.packages[""].version === version,
  "package-lock.json packages[\"\"] version does not match package.json",
);
assert(
  changelog.includes(`## ${version}`),
  `CHANGELOG.md is missing a ## ${version} entry`,
);
const firstChangelogHeading = changelog.match(/^##\s+(.+)$/m);
assert(
  firstChangelogHeading && firstChangelogHeading[1].trim() === version,
  `CHANGELOG.md must list ${version} as the newest release entry`,
);
assert(
  readme.includes("https://marketplace.visualstudio.com/items?itemName=unicompute.gemstone-py-workbench"),
  "README.md is missing the Visual Studio Marketplace URL",
);

const screenshotNames = [
  "examples-runner.png",
  "environment-checks.png",
  "database-explorer.png",
  "workbench-setup-flow.png",
];

for (const screenshotName of screenshotNames) {
  const screenshotPath = path.join(root, "media", "screenshots", screenshotName);
  assert(fs.existsSync(screenshotPath), `${screenshotName} is missing from media/screenshots`);
  assert(
    readme.includes(`/media/screenshots/${screenshotName}`),
    `README.md does not reference ${screenshotName}`,
  );
}

if (process.argv.includes("--vsix")) {
  const vsixFiles = findVsixFiles();
  const expectedName = `${packageName}-${version}.vsix`;
  assert(
    vsixFiles.includes(expectedName),
    `expected ${expectedName}; found ${vsixFiles.join(", ") || "no VSIX files"}`,
  );
  const vsixPackageJson = readVsixPackageJson(expectedName);
  assert(
    vsixPackageJson.name === packageName,
    `VSIX package name ${vsixPackageJson.name} does not match ${packageName}`,
  );
  assert(
    vsixPackageJson.version === version,
    `VSIX package version ${vsixPackageJson.version} does not match ${version}`,
  );
}

if (process.exitCode) {
  process.exit(process.exitCode);
}

console.log(`release preflight passed for ${packageName} ${version}`);
