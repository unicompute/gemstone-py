"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const Module = require("node:module");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const packageJson = require("../package.json");

let workspaceFolders = [{ uri: { fsPath: "/workspace/gemstone-py" } }];
let configurationValues = {};
let terminals = [];
let registeredCommands = new Map();
let warnings = [];
let clipboardText = "";

function resetState() {
  configurationValues = {
    pythonPath: "python3",
    repoPath: "/workspace/gemstone-py",
    explorerPath: "/workspace/python-gemstone-database-explorer",
    explorerHost: "127.0.0.1",
    explorerPort: 9292,
    env: {
      GS_STONE: "gs64stone",
      GS_PASSWORD: "secret",
      GEMSTONE_PY_SMOKE_EMPTY: "",
    },
  };
  workspaceFolders = [{ uri: { fsPath: "/workspace/gemstone-py" } }];
  terminals = [];
  registeredCommands = new Map();
  warnings = [];
  clipboardText = "";
}

class EventEmitter {
  constructor() {
    this.events = [];
    this.event = (listener) => {
      this.listener = listener;
      return { dispose() {} };
    };
  }

  fire(value) {
    this.events.push(value);
    if (this.listener) {
      this.listener(value);
    }
  }
}

class ThemeIcon {
  constructor(id) {
    this.id = id;
  }
}

class TreeItem {
  constructor(label, collapsibleState) {
    this.label = label;
    this.collapsibleState = collapsibleState;
  }
}

const fakeVscode = {
  EventEmitter,
  ThemeIcon,
  TreeItem,
  TreeItemCollapsibleState: {
    None: 0,
    Collapsed: 1,
    Expanded: 2,
  },
  Uri: {
    file(fsPath) {
      return { fsPath };
    },
    parse(value) {
      return { value, toString: () => value };
    },
  },
  commands: {
    registerCommand(command, callback) {
      registeredCommands.set(command, callback);
      return {
        dispose() {
          registeredCommands.delete(command);
        },
      };
    },
    executeCommand(command, ...args) {
      return Promise.resolve({ command, args });
    },
  },
  env: {
    clipboard: {
      writeText(value) {
        clipboardText = value;
        return Promise.resolve();
      },
    },
    openExternal() {
      return Promise.resolve(true);
    },
  },
  window: {
    createOutputChannel() {
      return {
        appendLine() {},
        clear() {},
        dispose() {},
        show() {},
      };
    },
    createTerminal(options) {
      const terminal = {
        options,
        sentText: [],
        shown: false,
        sendText(command) {
          this.sentText.push(command);
        },
        show() {
          this.shown = true;
        },
      };
      terminals.push(terminal);
      return terminal;
    },
    registerTreeDataProvider(viewId, provider) {
      return { viewId, provider, dispose() {} };
    },
    showInformationMessage() {
      return Promise.resolve();
    },
    showWarningMessage(message) {
      warnings.push(message);
      return Promise.resolve();
    },
  },
  workspace: {
    get workspaceFolders() {
      return workspaceFolders;
    },
    getConfiguration(section) {
      assert.equal(section, "gemstonePy");
      return {
        get(key) {
          return configurationValues[key];
        },
      };
    },
  },
};

const originalLoad = Module._load;
Module._load = function patchedLoad(request, parent, isMain) {
  if (request === "vscode") {
    return fakeVscode;
  }
  return originalLoad.call(this, request, parent, isMain);
};

const config = require("../out/config");
const terminal = require("../out/commands/terminal");
const actions = require("../out/commands/actions");
const providers = require("../out/views/providers");

test.beforeEach(resetState);

test("configuration helpers quote shell values and mask secrets", () => {
  assert.equal(config.shellQuote("simple_value-1"), "simple_value-1");
  assert.equal(config.shellQuote("two words"), "'two words'");
  assert.equal(config.shellQuote("it's"), "'it'\\''s'");
  assert.equal(config.maskEnvValue("GS_PASSWORD", "secret"), "********");
  assert.equal(config.maskEnvValue("GS_STONE", "gs64stone"), "gs64stone");
  assert.equal(config.maskEnvValue("GS_TOKEN", ""), "<empty>");

  assert.equal(
    config.envExportScript({
      GS_STONE: "stone one",
      GS_PASSWORD: "p'a",
      GEMSTONE_PY_SMOKE_EMPTY: "",
    }),
    "export GS_STONE='stone one'\nexport GS_PASSWORD='p'\\''a'",
  );
});

test("getConfig uses workspace defaults and normalizes environment values", () => {
  configurationValues = {
    pythonPath: " python3 ",
    repoPath: " ",
    explorerPath: " /tmp/explorer ",
    explorerHost: "",
    explorerPort: 0,
    env: {
      GS_STONE: "gs64stone",
      NULL_VALUE: null,
    },
  };

  const resolved = config.getConfig();
  assert.equal(resolved.pythonPath, "python3");
  assert.equal(resolved.repoPath, "/workspace/gemstone-py");
  assert.equal(resolved.explorerPath, "/tmp/explorer");
  assert.equal(resolved.explorerHost, "127.0.0.1");
  assert.equal(resolved.explorerPort, 9292);
  assert.deepEqual(resolved.env, {
    GS_STONE: "gs64stone",
    NULL_VALUE: "",
  });
});

test("runRepoPythonModule builds terminal command and drops empty env values", () => {
  terminal.runRepoPythonModule("Async example", "examples.async_features.demo", [
    "has space",
    "safe_arg",
  ]);

  assert.equal(terminals.length, 1);
  assert.equal(terminals[0].options.name, "GemStone: Async example");
  assert.equal(terminals[0].options.cwd, "/workspace/gemstone-py");
  assert.equal(terminals[0].options.env.GS_STONE, "gs64stone");
  assert.equal(terminals[0].options.env.GEMSTONE_PY_SMOKE_EMPTY, undefined);
  assert.equal(terminals[0].shown, true);
  assert.deepEqual(terminals[0].sentText, [
    "python3 -m examples.async_features.demo 'has space' safe_arg",
  ]);
});

test("runRepoScript includes explicit extra environment values", () => {
  terminal.runRepoScript("CI checks", "./scripts/run_ci_checks.sh", {
    GS_SKIP_BUILD_SMOKE: "1",
    GEMSTONE_PY_EXTRA_EMPTY: "",
  });

  assert.equal(terminals.length, 1);
  assert.equal(terminals[0].options.cwd, "/workspace/gemstone-py");
  assert.equal(terminals[0].options.env.GS_SKIP_BUILD_SMOKE, "1");
  assert.equal(terminals[0].options.env.GEMSTONE_PY_EXTRA_EMPTY, undefined);
  assert.deepEqual(terminals[0].sentText, ["./scripts/run_ci_checks.sh"]);
});

test("tree providers expose expected commands and mask environment secrets", () => {
  const examples = providers.createExamplesProvider().getChildren();
  assert.deepEqual(
    examples.map((item) => item.options.command),
    [
      "gemstonePy.runGrandTour",
      "gemstonePy.runHelloGemstone",
      "gemstonePy.runSmalltalkDemo",
      "gemstonePy.runAsyncExample",
      "gemstonePy.runTypedExample",
      "gemstonePy.runLifetimeExample",
      "gemstonePy.checkNativeBackend",
      "gemstonePy.runFastApiExample",
    ],
  );

  const environment = providers.createEnvironmentProvider().getChildren();
  const envGroup = environment.find((item) => item.label === "Configured environment");
  assert.ok(envGroup);
  const password = envGroup.children.find((item) => item.label === "GS_PASSWORD");
  assert.equal(password.options.description, "********");

  const ide = providers.createIdeProvider().getChildren();
  const explorer = ide.find((item) => item.label === "Python Database Explorer");
  assert.ok(explorer);
  assert.deepEqual(
    explorer.children.map((item) => item.options.command),
    [
      "gemstonePy.launchDatabaseExplorer",
      "gemstonePy.openDatabaseExplorer",
      "gemstonePy.runDatabaseExplorerTests",
      "gemstonePy.runDatabaseExplorerUiTests",
      "gemstonePy.runDatabaseExplorerLiveUiTests",
      "gemstonePy.openDatabaseExplorerRepository",
    ],
  );

  const treeItem = providers.createExamplesProvider().getTreeItem(examples[0]);
  assert.equal(treeItem.command.command, "gemstonePy.runGrandTour");
  assert.equal(treeItem.iconPath.id, "play");
});

test("registered commands match package contributions", () => {
  const context = { subscriptions: [] };
  actions.registerCommands(context, [{ refresh() {} }]);

  const contributedCommands = new Set(
    packageJson.contributes.commands.map((entry) => entry.command),
  );
  assert.deepEqual(new Set(registeredCommands.keys()), contributedCommands);
  assert.equal(context.subscriptions.length, contributedCommands.size + 1);
});

test("copyEnvScript copies only non-empty configured variables", async () => {
  await registeredCommand("gemstonePy.copyEnvScript")();

  assert.equal(
    clipboardText,
    "export GS_STONE=gs64stone\nexport GS_PASSWORD=secret",
  );
});

test("launchDatabaseExplorer warns when explorerPath is not configured", () => {
  configurationValues.explorerPath = "";
  registeredCommand("gemstonePy.launchDatabaseExplorer")();

  assert.equal(terminals.length, 0);
  assert.deepEqual(warnings, [
    "Set gemstonePy.explorerPath before launching the database explorer.",
  ]);
});

test("launchDatabaseExplorer starts Python directly without shell sendText", () => {
  const explorerPath = fs.mkdtempSync(path.join(os.tmpdir(), "gemstone-explorer-"));
  const pythonPath = path.join(explorerPath, ".venv", "bin", "python");
  fs.mkdirSync(path.dirname(pythonPath), { recursive: true });
  fs.writeFileSync(pythonPath, "");

  configurationValues.explorerPath = explorerPath;
  registeredCommand("gemstonePy.launchDatabaseExplorer")();

  assert.equal(terminals.length, 1);
  assert.equal(terminals[0].options.name, "GemStone: Database explorer");
  assert.equal(terminals[0].options.cwd, explorerPath);
  assert.equal(terminals[0].options.shellPath, pythonPath);
  assert.deepEqual(terminals[0].options.shellArgs, [
    "-m",
    "gemstone_p.cli",
    "--host",
    "127.0.0.1",
    "--port",
    "9292",
  ]);
  assert.deepEqual(terminals[0].sentText, []);
  assert.equal(terminals[0].shown, true);
});

function registeredCommand(command) {
  const context = { subscriptions: [] };
  actions.registerCommands(context, [{ refresh() {} }]);
  const callback = registeredCommands.get(command);
  assert.ok(callback, `expected ${command} to be registered`);
  return callback;
}
