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
let executedCommands = [];
let openedExternal = [];
let extensionsById = new Map();
let warnings = [];
let clipboardText = "";
let inputBoxValues = [];
let informationMessages = [];
let informationMessageSelection;
let configUpdates = [];
let refreshedProviders = 0;
let outputLines = [];
let outputShown = false;
let webviewPanels = [];
let webviewMessages = [];

function resetState() {
  configurationValues = {
    pythonPath: "python3",
    repoPath: "/workspace/gemstone-py",
    explorerPath: "/workspace/python-gemstone-database-explorer",
    explorerHost: "127.0.0.1",
    explorerPort: 9292,
    env: {
      GS_STONE: "gs64stone",
      GS_STONE_NAME: "gs64stone",
      GS_USERNAME: "DataCurator",
      GS_PASSWORD: "secret",
      GEMSTONE_PY_SMOKE_EMPTY: "",
    },
  };
  workspaceFolders = [{ uri: { fsPath: "/workspace/gemstone-py" } }];
  terminals = [];
  registeredCommands = new Map();
  executedCommands = [];
  openedExternal = [];
  extensionsById = new Map();
  warnings = [];
  clipboardText = "";
  inputBoxValues = [];
  informationMessages = [];
  informationMessageSelection = undefined;
  configUpdates = [];
  refreshedProviders = 0;
  outputLines = [];
  outputShown = false;
  webviewPanels = [];
  webviewMessages = [];
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
  ViewColumn: {
    One: 1,
  },
  ConfigurationTarget: {
    Global: 1,
    Workspace: 2,
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
    getCommands() {
      return Promise.resolve(Array.from(registeredCommands.keys()));
    },
    executeCommand(command, ...args) {
      executedCommands.push({ command, args });
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
    openExternal(uri) {
      openedExternal.push(uri);
      return Promise.resolve(true);
    },
  },
  extensions: {
    getExtension(id) {
      return extensionsById.get(id);
    },
  },
  window: {
    createOutputChannel() {
      return {
        appendLine(value = "") {
          outputLines.push(String(value));
        },
        clear() {
          outputLines = [];
        },
        dispose() {},
        show() {
          outputShown = true;
        },
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
    createWebviewPanel(viewType, title, column, options) {
      const panel = {
        viewType,
        title,
        column,
        options,
        webview: {
          html: "",
          postMessage(message) {
            webviewMessages.push(message);
            return Promise.resolve(true);
          },
          onDidReceiveMessage(callback) {
            this.messageHandler = callback;
            return { dispose() {} };
          },
        },
      };
      webviewPanels.push(panel);
      return panel;
    },
    registerTreeDataProvider(viewId, provider) {
      return { viewId, provider, dispose() {} };
    },
    showInformationMessage(message) {
      informationMessages.push(message);
      return Promise.resolve(informationMessageSelection);
    },
    showInputBox(options) {
      const value = inputBoxValues.shift();
      return Promise.resolve(value === undefined ? undefined : value);
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
        update(key, value, target) {
          configurationValues[key] = value;
          configUpdates.push({ key, value, target });
          return Promise.resolve();
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
      GS_STONE_NAME: "stone one",
      GS_PASSWORD: "p'a",
      GEMSTONE_PY_SMOKE_EMPTY: "",
    }),
    "export GS_STONE='stone one'\nexport GS_STONE_NAME='stone one'\nexport GS_PASSWORD='p'\\''a'",
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

test("getConfig uses a workspace .venv Python when pythonPath is empty", () => {
  const workspacePath = fs.mkdtempSync(path.join(os.tmpdir(), "gemstone-py-"));
  const pythonPath = path.join(workspacePath, ".venv", "bin", "python");
  fs.mkdirSync(path.dirname(pythonPath), { recursive: true });
  fs.writeFileSync(pythonPath, "");
  workspaceFolders = [{ uri: { fsPath: workspacePath } }];
  configurationValues.pythonPath = "";
  configurationValues.repoPath = "";

  const resolved = config.getConfig();

  assert.equal(resolved.repoPath, workspacePath);
  assert.equal(resolved.pythonPath, pythonPath);
});

test("getConfig detects a gemstone-py child checkout from a parent workspace", () => {
  const workspacePath = fs.mkdtempSync(path.join(os.tmpdir(), "workspace-"));
  const checkoutPath = path.join(workspacePath, "gemstone-py");
  const pythonPath = path.join(checkoutPath, ".venv", "bin", "python");
  fs.mkdirSync(path.join(checkoutPath, "gemstone_py"), { recursive: true });
  fs.mkdirSync(path.join(checkoutPath, "examples"), { recursive: true });
  fs.mkdirSync(path.dirname(pythonPath), { recursive: true });
  fs.writeFileSync(path.join(checkoutPath, "pyproject.toml"), "[project]\n");
  fs.writeFileSync(pythonPath, "");
  workspaceFolders = [{ uri: { fsPath: workspacePath } }];
  configurationValues.pythonPath = "";
  configurationValues.repoPath = "";

  const resolved = config.getConfig();

  assert.equal(resolved.repoPath, checkoutPath);
  assert.equal(resolved.pythonPath, pythonPath);
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

test("runFastApiExample uses the dependency-checking repository runner", () => {
  registeredCommand("gemstonePy.runFastApiExample")();

  assert.equal(terminals.length, 1);
  assert.equal(terminals[0].options.name, "GemStone: FastAPI example");
  assert.equal(terminals[0].options.cwd, "/workspace/gemstone-py");
  assert.deepEqual(terminals[0].sentText, [
    "python3 -m examples.fastapi.run --reload",
  ]);
});

test("new example commands use repository runners", () => {
  registeredCommand("gemstonePy.listExamples")();
  registeredCommand("gemstonePy.runQuickstartExample")();
  registeredCommand("gemstonePy.runLitestarExample")();
  registeredCommand("gemstonePy.showPlan3FeatureMap")();

  assert.equal(terminals.length, 4);
  assert.deepEqual(
    terminals.map((terminal) => terminal.options.name),
    [
      "GemStone: Example catalog",
      "GemStone: Quickstart",
      "GemStone: Litestar example",
      "GemStone: Plan3 feature map",
    ],
  );
  assert.deepEqual(
    terminals.map((terminal) => terminal.sentText[0]),
    [
      "python3 -m gemstone_py.cli list",
      "python3 -m examples.quickstart",
      "python3 -m examples.litestar.run --reload",
      "python3 -m examples.cookbook.plan3_feature_map",
    ],
  );
});

test("codegen commands use repository workflows", async () => {
  const repoPath = fs.mkdtempSync(path.join(os.tmpdir(), "gemstone-py-"));
  const docsPath = path.join(repoPath, "docs");
  fs.mkdirSync(docsPath, { recursive: true });
  fs.writeFileSync(path.join(docsPath, "codegen.md"), "# Codegen\n");
  configurationValues.repoPath = repoPath;

  registeredCommand("gemstonePy.runCodegenCheck")();
  registeredCommand("gemstonePy.generateCodegenWrappers")();
  registeredCommand("gemstonePy.runCodegenFastApiDemo")();
  await registeredCommand("gemstonePy.openCodegenDocs")();

  assert.deepEqual(
    terminals.map((terminal) => terminal.options.name),
    [
      "GemStone: Codegen check",
      "GemStone: Generate codegen wrappers",
      "GemStone: Codegen FastAPI demo",
    ],
  );
  assert.deepEqual(
    terminals.map((terminal) => terminal.sentText[0]),
    [
      "python3 -m gemstone_py.codegen --module examples.typed_access.codegen_demo.models --output examples/typed_access/codegen_demo/generated --check",
      "python3 -m gemstone_py.codegen --module examples.typed_access.codegen_demo.models --output examples/typed_access/codegen_demo/generated --clean",
      "python3 -m examples.typed_access.codegen_demo.run --reload",
    ],
  );
  assert.deepEqual(executedCommands, [
    {
      command: "vscode.open",
      args: [{ fsPath: path.join(repoPath, "docs", "codegen.md") }],
    },
  ]);
});

test("tree providers expose expected commands and mask environment secrets", () => {
  const examples = providers.createExamplesProvider().getChildren();
  assert.deepEqual(
    examples.map((item) => item.options.command),
    [
      "gemstonePy.runGrandTour",
      "gemstonePy.listExamples",
      "gemstonePy.runHelloGemstone",
      "gemstonePy.runQuickstartExample",
      "gemstonePy.runSmalltalkDemo",
      "gemstonePy.runAsyncExample",
      "gemstonePy.runTypedExample",
      "gemstonePy.runCodegenCheck",
      "gemstonePy.generateCodegenWrappers",
      "gemstonePy.runCodegenFastApiDemo",
      "gemstonePy.openCodegenDocs",
      "gemstonePy.openCodegenExplorer",
      "gemstonePy.runLifetimeExample",
      "gemstonePy.checkNativeBackend",
      "gemstonePy.runFastApiExample",
      "gemstonePy.runLitestarExample",
      "gemstonePy.showPlan3FeatureMap",
    ],
  );

  const docs = providers.createDocsProvider().getChildren();
  assert.ok(
    docs.find((item) => item.options.command === "gemstonePy.openFrameworkAdapters"),
  );
  assert.ok(
    docs.find((item) => item.options.command === "gemstonePy.openPlan3FeatureMap"),
  );
  assert.ok(
    docs.find((item) => item.options.command === "gemstonePy.openCodegenDocs"),
  );

  const environment = providers.createEnvironmentProvider().getChildren();
  assert.ok(
    environment.find((item) => item.options.command === "gemstonePy.configureWorkbench"),
  );
  assert.ok(
    environment.find(
      (item) => item.options.command === "gemstonePy.verifyWorkbenchSetup",
    ),
  );
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
      "gemstonePy.openDatabaseExplorerWebview",
      "gemstonePy.runDatabaseExplorerTests",
      "gemstonePy.runDatabaseExplorerUiTests",
      "gemstonePy.runDatabaseExplorerLiveUiTests",
      "gemstonePy.openDatabaseExplorerRepository",
    ],
  );

  const codegen = ide.find((item) => item.label === "Codegen");
  assert.ok(codegen);
  assert.deepEqual(
    codegen.children.map((item) => item.options.command),
    [
      "gemstonePy.openCodegenExplorer",
      "gemstonePy.runCodegenCheck",
      "gemstonePy.generateCodegenWrappers",
      "gemstonePy.runCodegenFastApiDemo",
    ],
  );

  const jasper = ide.find((item) => item.label === "Jasper");
  assert.ok(jasper);
  assert.deepEqual(
    jasper.children.map((item) => item.options.command),
    [
      "gemstonePy.openJasper",
      "gemstonePy.openJasper",
      "gemstonePy.openJasperRepository",
    ],
  );
  const jasperHandoff = jasper.children.find(
    (item) => item.label === "Use Jasper for Smalltalk IDE work",
  );
  assert.ok(jasperHandoff);
  assert.equal(
    providers.createIdeProvider().getTreeItem(jasperHandoff).command.command,
    "gemstonePy.openJasper",
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

test("package contributes command palette titles for Codegen commands", () => {
  const titlesByCommand = new Map(
    packageJson.contributes.commands.map((entry) => [entry.command, entry.title]),
  );

  assert.equal(
    titlesByCommand.get("gemstonePy.runCodegenCheck"),
    "GemStone: Run Codegen Check",
  );
  assert.equal(
    titlesByCommand.get("gemstonePy.generateCodegenWrappers"),
    "GemStone: Generate Codegen Wrappers",
  );
  assert.equal(
    titlesByCommand.get("gemstonePy.runCodegenFastApiDemo"),
    "GemStone: Run Codegen FastAPI Demo",
  );
  assert.equal(
    titlesByCommand.get("gemstonePy.openCodegenDocs"),
    "GemStone: Open Codegen Docs",
  );
  assert.equal(
    titlesByCommand.get("gemstonePy.openCodegenExplorer"),
    "GemStone: Open Codegen Explorer",
  );
});

test("package activation events include Codegen commands", () => {
  assert.ok(packageJson.activationEvents.includes("onCommand:gemstonePy.runCodegenCheck"));
  assert.ok(
    packageJson.activationEvents.includes(
      "onCommand:gemstonePy.generateCodegenWrappers",
    ),
  );
  assert.ok(
    packageJson.activationEvents.includes("onCommand:gemstonePy.runCodegenFastApiDemo"),
  );
  assert.ok(packageJson.activationEvents.includes("onCommand:gemstonePy.openCodegenDocs"));
  assert.ok(
    packageJson.activationEvents.includes("onCommand:gemstonePy.openCodegenExplorer"),
  );
});

test("openJasper activates installed Jasper and opens the GemStone sidebar", async () => {
  const jasper = {
    activated: false,
    activate() {
      this.activated = true;
      return Promise.resolve({});
    },
  };
  extensionsById.set("gemtalksystems.gemstone-ide", jasper);

  const result = await registeredCommand("gemstonePy.openJasper")();

  assert.equal(jasper.activated, true);
  assert.equal(result, "jasper-sidebar");
  assert.deepEqual(executedCommands, [
    { command: "workbench.view.extension.gemstone", args: [] },
  ]);
  assert.deepEqual(openedExternal, []);
});

test("verifyWorkbenchSetup reports installed Jasper handoff status", async () => {
  const jasper = {
    isActive: true,
    activate() {
      return Promise.resolve({});
    },
  };
  extensionsById.set("gemtalksystems.gemstone-ide", jasper);
  registeredCommands.set("workbench.view.extension.gemstone", () =>
    Promise.resolve("opened"),
  );
  configurationValues.env.GS_PASSWORD = "";

  const result = await registeredCommand("gemstonePy.verifyWorkbenchSetup")();

  assert.ok(
    result.find(
      (check) =>
        check.name === "Jasper IDE handoff" &&
        check.status === "ok" &&
        check.detail.includes("GemStone sidebar opened"),
    ),
  );
  assert.ok(
    executedCommands.find(
      (entry) => entry.command === "workbench.view.extension.gemstone",
    ),
  );
});

test("openJasper opens the VS Code Extensions view when Jasper is not installed", async () => {
  const result = await registeredCommand("gemstonePy.openJasper")();

  assert.equal(result, "extensions-search");
  assert.deepEqual(executedCommands, [
    {
      command: "workbench.extensions.search",
      args: ["@id:GemTalkSystems.gemstone-ide"],
    },
  ]);
  assert.deepEqual(openedExternal, []);
});

test("openJasperRepository opens the Jasper source repository", async () => {
  await registeredCommand("gemstonePy.openJasperRepository")();

  assert.equal(openedExternal.length, 1);
  assert.equal(openedExternal[0].toString(), "https://github.com/jgfoster/Jasper");
});

test("copyEnvScript copies only non-empty configured variables", async () => {
  await registeredCommand("gemstonePy.copyEnvScript")();

  assert.equal(
    clipboardText,
    "export GS_STONE=gs64stone\nexport GS_STONE_NAME=gs64stone\nexport GS_USERNAME=DataCurator\nexport GS_PASSWORD=secret",
  );
});

test("launchDatabaseExplorer warns when explorerPath is not configured", () => {
  configurationValues.explorerPath = "";
  const result = registeredCommand("gemstonePy.launchDatabaseExplorer")();

  assert.equal(result, false);
  assert.equal(terminals.length, 0);
  assert.deepEqual(warnings, [
    "Set gemstonePy.explorerPath before launching the database explorer.",
  ]);
});

test("launchDatabaseExplorer warns when GemStone credentials are not configured", () => {
  const explorerPath = fs.mkdtempSync(path.join(os.tmpdir(), "gemstone-explorer-"));
  configurationValues.explorerPath = explorerPath;
  configurationValues.env.GS_PASSWORD = "";

  const result = registeredCommand("gemstonePy.launchDatabaseExplorer")();

  assert.equal(result, false);
  assert.equal(terminals.length, 0);
  assert.deepEqual(warnings, [
    "Set gemstonePy.env.GS_PASSWORD before launching the database explorer.",
  ]);
});

test("launchDatabaseExplorer starts Python directly without shell sendText", () => {
  const explorerPath = fs.mkdtempSync(path.join(os.tmpdir(), "gemstone-explorer-"));
  const pythonPath = path.join(explorerPath, ".venv", "bin", "python");
  fs.mkdirSync(path.dirname(pythonPath), { recursive: true });
  fs.writeFileSync(pythonPath, "");

  configurationValues.explorerPath = explorerPath;
  const result = registeredCommand("gemstonePy.launchDatabaseExplorer")();

  assert.equal(result, true);
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
  assert.equal(terminals[0].options.env.GS_PASSWORD, "secret");
  assert.equal(terminals[0].shown, true);
});

test("openDatabaseExplorerWebview embeds the configured explorer URL", () => {
  const result = registeredCommand("gemstonePy.openDatabaseExplorerWebview")();

  assert.equal(result, "http://127.0.0.1:9292/");
  assert.equal(webviewPanels.length, 1);
  assert.equal(webviewPanels[0].viewType, "gemstonePyDatabaseExplorer");
  assert.equal(webviewPanels[0].title, "GemStone Database Explorer");
  assert.match(webviewPanels[0].webview.html, /<iframe/);
  assert.match(webviewPanels[0].webview.html, /http:\/\/127\.0\.0\.1:9292\//);
});

test("openCodegenExplorer creates a visual codegen webview", () => {
  const result = registeredCommand("gemstonePy.openCodegenExplorer")();

  assert.equal(result, "http://127.0.0.1:9292/");
  assert.equal(webviewPanels.length, 1);
  assert.equal(webviewPanels[0].viewType, "gemstonePyCodegenExplorer");
  assert.equal(webviewPanels[0].title, "GemStone Codegen Explorer");
  assert.match(webviewPanels[0].webview.html, /Codegen Explorer/);
  assert.match(webviewPanels[0].webview.html, /Preview Wrappers/);
  assert.match(webviewPanels[0].webview.html, /Diff Output/);
  assert.match(webviewPanels[0].webview.html, /Test Live Targets/);
  assert.equal(typeof webviewPanels[0].webview.messageHandler, "function");
});

test("configureWorkbench writes workspace settings and refreshes views", async () => {
  inputBoxValues = [
    "/workspace/gemstone-py/.venv/bin/python",
    "/workspace/gemstone-py",
    "/workspace/python-gemstone-database-explorer",
    "SystemUser",
    "configured password",
    "seaside",
  ];

  const result = await registeredCommand("gemstonePy.configureWorkbench")();

  assert.equal(result, "configured");
  assert.deepEqual(
    configUpdates.map((update) => [update.key, update.target]),
    [
      ["pythonPath", fakeVscode.ConfigurationTarget.Workspace],
      ["repoPath", fakeVscode.ConfigurationTarget.Workspace],
      ["explorerPath", fakeVscode.ConfigurationTarget.Workspace],
      ["env", fakeVscode.ConfigurationTarget.Workspace],
    ],
  );
  assert.equal(configurationValues.pythonPath, "/workspace/gemstone-py/.venv/bin/python");
  assert.equal(configurationValues.repoPath, "/workspace/gemstone-py");
  assert.equal(
    configurationValues.explorerPath,
    "/workspace/python-gemstone-database-explorer",
  );
  assert.equal(configurationValues.env.GS_USERNAME, "SystemUser");
  assert.equal(configurationValues.env.GS_PASSWORD, "configured password");
  assert.equal(configurationValues.env.GS_STONE_NAME, "seaside");
  assert.equal(configurationValues.env.GS_STONE, "seaside");
  assert.equal(refreshedProviders, 1);
  assert.deepEqual(informationMessages, ["gemstone-py Workbench settings updated."]);
});

test("verifyWorkbenchSetup reports paths packages and skipped connectivity", async () => {
  configurationValues.env.GS_PASSWORD = "";

  const result = await registeredCommand("gemstonePy.verifyWorkbenchSetup")();

  assert.equal(outputShown, true);
  assert.ok(Array.isArray(result));
  assert.ok(result.find((check) => check.name === "Python executable"));
  assert.ok(result.find((check) => check.name === "Native backend package"));
  assert.ok(
    result.find(
      (check) =>
        check.name === "GemStone connectivity" &&
        check.status === "warning" &&
        check.detail.includes("skipped"),
    ),
  );
  assert.match(outputLines.join("\n"), /Workbench setup verification/);
  assert.deepEqual(informationMessages, [
    "gemstone-py setup verification complete.",
  ]);
  assert.equal(terminals.length, 0);
});

test("verifyWorkbenchSetup can copy the current report from its action", async () => {
  informationMessageSelection = "Copy Report";
  configurationValues.env.GS_PASSWORD = "";

  await registeredCommand("gemstonePy.verifyWorkbenchSetup")();
  await waitForAsyncActions();

  assert.match(clipboardText, /gemstone-py Workbench setup verification/);
  assert.match(clipboardText, /Actions: Open Settings, Copy Report/);
  assert.deepEqual(informationMessages, [
    "gemstone-py setup verification complete.",
    "Copied gemstone-py setup verification report.",
  ]);
});

test("verifyWorkbenchSetup can open settings from its action", async () => {
  informationMessageSelection = "Open Settings";
  configurationValues.env.GS_PASSWORD = "";

  await registeredCommand("gemstonePy.verifyWorkbenchSetup")();
  await waitForAsyncActions();

  assert.ok(
    executedCommands.find(
      (entry) =>
        entry.command === "workbench.action.openSettings" &&
        entry.args[0] === "@ext:unicompute.gemstone-py-workbench",
    ),
  );
});

test("configureWorkbench cancels without writing settings", async () => {
  inputBoxValues = [undefined];

  const result = await registeredCommand("gemstonePy.configureWorkbench")();

  assert.equal(result, "cancelled");
  assert.deepEqual(configUpdates, []);
});

function registeredCommand(command) {
  const context = { subscriptions: [] };
  actions.registerCommands(context, [{ refresh() { refreshedProviders += 1; } }]);
  const callback = registeredCommands.get(command);
  assert.ok(callback, `expected ${command} to be registered`);
  return callback;
}

function waitForAsyncActions() {
  return new Promise((resolve) => setImmediate(resolve));
}
