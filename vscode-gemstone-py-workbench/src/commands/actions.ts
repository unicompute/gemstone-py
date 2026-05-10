import { execFile } from "child_process";
import { promisify } from "util";
import * as vscode from "vscode";
import {
  buildEnv,
  envExportScript,
  explorerPython,
  getConfig,
  maskEnvValue,
  pathExists,
  repoFile,
  shellQuote,
} from "../config";
import { WorkbenchTreeProvider } from "../views/providers";
import {
  runInTerminal,
  runProcessInTerminal,
  runRepoPythonModule,
  runRepoScript,
} from "./terminal";

const JASPER_EXTENSION_ID = "gemtalksystems.gemstone-ide";
const JASPER_MARKETPLACE_ID = "GemTalkSystems.gemstone-ide";
const JASPER_REPOSITORY_URL = "https://github.com/jgfoster/Jasper";
const JASPER_VIEW_COMMAND = "workbench.view.extension.gemstone";

const execFileAsync = promisify(execFile);
const output = vscode.window.createOutputChannel("gemstone-py Workbench");

export function registerCommands(
  context: vscode.ExtensionContext,
  providers: WorkbenchTreeProvider[],
): void {
  context.subscriptions.push(output);

  const subscriptions = [
    vscode.commands.registerCommand("gemstonePy.refreshViews", () => {
      providers.forEach((provider) => provider.refresh());
    }),
    vscode.commands.registerCommand("gemstonePy.runGrandTour", () =>
      runRepoPythonModule("Grand tour", "examples.example"),
    ),
    vscode.commands.registerCommand("gemstonePy.runHelloGemstone", () =>
      runRepoPythonModule("Hello GemStone", "examples.hello_gemstone"),
    ),
    vscode.commands.registerCommand("gemstonePy.runSmalltalkDemo", () =>
      runRepoPythonModule("Smalltalk demo", "examples.misc.smalltalk_demo"),
    ),
    vscode.commands.registerCommand("gemstonePy.runAsyncExample", () =>
      runRepoPythonModule(
        "Async example",
        "examples.async_features.session_root_and_collection",
      ),
    ),
    vscode.commands.registerCommand("gemstonePy.runTypedExample", () =>
      runRepoPythonModule(
        "Typed OOP example",
        "examples.typed_access.typed_oops_and_queries",
      ),
    ),
    vscode.commands.registerCommand("gemstonePy.runLifetimeExample", () =>
      runRepoPythonModule(
        "Managed lifetime example",
        "examples.lifetime.managed_oop_handles",
      ),
    ),
    vscode.commands.registerCommand("gemstonePy.checkNativeBackend", () =>
      runRepoPythonModule("Native backend check", "examples.native_backend.check_backend"),
    ),
    vscode.commands.registerCommand("gemstonePy.runFastApiExample", runFastApiExample),
    vscode.commands.registerCommand("gemstonePy.showEnvironment", showEnvironment),
    vscode.commands.registerCommand("gemstonePy.configureWorkbench", () =>
      configureWorkbench(providers),
    ),
    vscode.commands.registerCommand("gemstonePy.copyEnvScript", copyEnvScript),
    vscode.commands.registerCommand("gemstonePy.checkBackend", checkBackend),
    vscode.commands.registerCommand("gemstonePy.openReadme", () => openRepoFile("README.md")),
    vscode.commands.registerCommand("gemstonePy.openSetupGuide", () =>
      openRepoFile("docs/setup-guide.md"),
    ),
    vscode.commands.registerCommand("gemstonePy.launchDatabaseExplorer", launchExplorer),
    vscode.commands.registerCommand("gemstonePy.openDatabaseExplorer", openExplorer),
    vscode.commands.registerCommand(
      "gemstonePy.runDatabaseExplorerTests",
      runExplorerTests,
    ),
    vscode.commands.registerCommand(
      "gemstonePy.runDatabaseExplorerUiTests",
      runExplorerUiTests,
    ),
    vscode.commands.registerCommand(
      "gemstonePy.runDatabaseExplorerLiveUiTests",
      runExplorerLiveUiTests,
    ),
    vscode.commands.registerCommand("gemstonePy.openDatabaseExplorerRepository", () =>
      vscode.env.openExternal(
        vscode.Uri.parse("https://github.com/unicompute/python-gemstone-database-explorer"),
      ),
    ),
    vscode.commands.registerCommand("gemstonePy.openExamplesGuide", () =>
      openRepoFile("docs/examples-guide.md"),
    ),
    vscode.commands.registerCommand("gemstonePy.openUserManual", () =>
      openRepoFile("docs/user-manual.md"),
    ),
    vscode.commands.registerCommand("gemstonePy.openMediumArticle", () =>
      openRepoFile("docs/medium-article.md"),
    ),
    vscode.commands.registerCommand("gemstonePy.openMediumArticlePdf", () =>
      openRepoFile("docs/pdf/medium-article.pdf"),
    ),
    vscode.commands.registerCommand("gemstonePy.rebuildDocsPdf", () =>
      runInTerminal(
        "Rebuild docs PDFs",
        `${shellQuote(getConfig().pythonPath)} docs/build_pdf_docs.py`,
        getConfig().repoPath,
      ),
    ),
    vscode.commands.registerCommand("gemstonePy.runCiChecks", () =>
      runRepoScript("CI checks", "./scripts/run_ci_checks.sh", {
        GS_SKIP_BUILD_SMOKE: "1",
      }),
    ),
    vscode.commands.registerCommand("gemstonePy.runLiveChecks", () =>
      runRepoScript("Live checks", "./scripts/run_live_checks.sh", {
        GS_RUN_LIVE: "1",
      }),
    ),
    vscode.commands.registerCommand("gemstonePy.runBenchmarks", () =>
      runRepoScript("Benchmarks", "./scripts/run_benchmarks.sh"),
    ),
    vscode.commands.registerCommand("gemstonePy.runNativeChecks", () =>
      runRepoScript("Native checks", "./scripts/run_native_checks.sh"),
    ),
    vscode.commands.registerCommand("gemstonePy.openJasper", openJasper),
    vscode.commands.registerCommand("gemstonePy.openJasperRepository", () =>
      vscode.env.openExternal(vscode.Uri.parse(JASPER_REPOSITORY_URL)),
    ),
  ];

  context.subscriptions.push(...subscriptions);
}

function runFastApiExample(): void {
  runRepoPythonModule("FastAPI example", "examples.fastapi.run", ["--reload"]);
}

async function configureWorkbench(
  providers: WorkbenchTreeProvider[],
): Promise<"configured" | "cancelled"> {
  const config = getConfig();
  const target = vscode.workspace.workspaceFolders?.length
    ? vscode.ConfigurationTarget.Workspace
    : vscode.ConfigurationTarget.Global;

  const pythonPath = await promptForSetting({
    title: "Configure gemstone-py Workbench",
    prompt: "Python executable for examples and checks.",
    value: config.pythonPath,
  });
  if (pythonPath === undefined) {
    return "cancelled";
  }

  const repoPath = await promptForSetting({
    title: "Configure gemstone-py Workbench",
    prompt: "Local gemstone-py checkout path.",
    value: config.repoPath,
  });
  if (repoPath === undefined) {
    return "cancelled";
  }

  const explorerPath = await promptForSetting({
    title: "Configure gemstone-py Workbench",
    prompt: "Local python-gemstone-database-explorer checkout path.",
    value: config.explorerPath,
  });
  if (explorerPath === undefined) {
    return "cancelled";
  }

  const username = await promptForSetting({
    title: "Configure gemstone-py Workbench",
    prompt: "GemStone username.",
    value: config.env.GS_USERNAME ?? "DataCurator",
  });
  if (username === undefined) {
    return "cancelled";
  }

  const password = await promptForSetting({
    title: "Configure gemstone-py Workbench",
    prompt: "GemStone password.",
    value: config.env.GS_PASSWORD ?? "",
    password: true,
    trim: false,
  });
  if (password === undefined) {
    return "cancelled";
  }

  const stoneName = await promptForSetting({
    title: "Configure gemstone-py Workbench",
    prompt: "GemStone stone name.",
    value: config.env.GS_STONE_NAME ?? config.env.GS_STONE ?? "gs64stone",
  });
  if (stoneName === undefined) {
    return "cancelled";
  }

  const nextEnv = {
    ...config.env,
    GS_USERNAME: username,
    GS_PASSWORD: password,
    GS_STONE_NAME: stoneName,
    GS_STONE: stoneName,
  };
  const configuration = vscode.workspace.getConfiguration("gemstonePy");
  await configuration.update("pythonPath", pythonPath, target);
  await configuration.update("repoPath", repoPath, target);
  await configuration.update("explorerPath", explorerPath, target);
  await configuration.update("env", nextEnv, target);
  providers.forEach((provider) => provider.refresh());
  void vscode.window.showInformationMessage("gemstone-py Workbench settings updated.");
  return "configured";
}

async function promptForSetting(options: {
  title: string;
  prompt: string;
  value: string;
  password?: boolean;
  trim?: boolean;
}): Promise<string | undefined> {
  const value = await vscode.window.showInputBox({
    title: options.title,
    prompt: options.prompt,
    value: options.value,
    password: options.password,
    ignoreFocusOut: true,
  });
  if (value === undefined) {
    return undefined;
  }
  return options.trim === false ? value : value.trim();
}

async function showEnvironment(): Promise<void> {
  const config = getConfig();
  output.clear();
  output.appendLine("gemstone-py Workbench environment");
  output.appendLine("");
  output.appendLine(`Python: ${config.pythonPath}`);
  output.appendLine(`Repository: ${config.repoPath} (${status(config.repoPath)})`);
  output.appendLine(
    `Database explorer: ${config.explorerPath} (${status(config.explorerPath)})`,
  );
  output.appendLine(`Explorer URL: http://${config.explorerHost}:${config.explorerPort}/`);
  output.appendLine("");
  output.appendLine("Configured environment:");
  for (const [key, value] of Object.entries(config.env)) {
    output.appendLine(`  ${key}=${maskEnvValue(key, value)}`);
  }

  output.appendLine("");
  output.appendLine("Python package probe:");
  const probe = await probePython();
  for (const [key, value] of Object.entries(probe)) {
    output.appendLine(`  ${key}: ${value}`);
  }
  output.show(true);
}

async function copyEnvScript(): Promise<void> {
  const config = getConfig();
  const script = envExportScript(config.env);
  await vscode.env.clipboard.writeText(script);
  void vscode.window.showInformationMessage("Copied gemstone-py environment exports.");
}

async function checkBackend(): Promise<void> {
  const probe = await probePython();
  const backend = probe.gci_backend ?? "unknown";
  output.clear();
  output.appendLine("GCI backend probe");
  output.appendLine(`backend: ${backend}`);
  output.appendLine(`gemstone_py: ${probe.gemstone_py ?? "unknown"}`);
  output.appendLine(`gemstone_py_native: ${probe.gemstone_py_native ?? "unknown"}`);
  output.show(true);
  void vscode.window.showInformationMessage(`gemstone-py backend: ${backend}`);
}

async function openRepoFile(relativePath: string): Promise<void> {
  const config = getConfig();
  const filePath = repoFile(config, relativePath);
  if (!pathExists(filePath)) {
    void vscode.window.showWarningMessage(`File does not exist: ${filePath}`);
    return;
  }
  await vscode.commands.executeCommand("vscode.open", vscode.Uri.file(filePath));
}

function launchExplorer(): boolean {
  const config = getConfig();
  if (!ensureExplorerPath(config.explorerPath)) {
    return false;
  }
  if (!ensureExplorerCredentials(config.env)) {
    return false;
  }

  const python = explorerPython(config);
  const args = [
    "-m",
    "gemstone_p.cli",
    "--host",
    config.explorerHost,
    "--port",
    String(config.explorerPort),
  ];
  runProcessInTerminal("Database explorer", python, args, config.explorerPath);
  return true;
}

async function openExplorer(): Promise<void> {
  const config = getConfig();
  await vscode.env.openExternal(
    vscode.Uri.parse(`http://${config.explorerHost}:${config.explorerPort}/`),
  );
}

async function openJasper(): Promise<"jasper-sidebar" | "extensions-search"> {
  const jasper = getJasperExtension();
  if (!jasper) {
    await vscode.commands.executeCommand(
      "workbench.extensions.search",
      `@id:${JASPER_MARKETPLACE_ID}`,
    );
    void vscode.window.showInformationMessage(
      `Install Jasper (${JASPER_MARKETPLACE_ID}) from the Extensions view, then open the GemStone sidebar.`,
    );
    return "extensions-search";
  }

  await jasper.activate();
  try {
    await vscode.commands.executeCommand(JASPER_VIEW_COMMAND);
    return "jasper-sidebar";
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    output.appendLine(`Could not open Jasper GemStone sidebar: ${message}`);
    output.show(true);
    void vscode.window.showWarningMessage(
      "Jasper is installed, but the GemStone sidebar could not be opened. Open the GemStone activity bar item manually.",
    );
    return "jasper-sidebar";
  }
}

function getJasperExtension(): vscode.Extension<unknown> | undefined {
  return (
    vscode.extensions.getExtension(JASPER_EXTENSION_ID) ??
    vscode.extensions.getExtension(JASPER_MARKETPLACE_ID)
  );
}

function runExplorerTests(): void {
  const config = getConfig();
  if (!ensureExplorerPath(config.explorerPath)) {
    return;
  }

  const python = explorerPython(config);
  runInTerminal(
    "Database explorer tests",
    `${shellQuote(python)} -m pytest -q`,
    config.explorerPath,
  );
}

function runExplorerUiTests(): void {
  const config = getConfig();
  if (!ensureExplorerPath(config.explorerPath)) {
    return;
  }

  runInTerminal("Database explorer UI tests", "npm run test:ui", config.explorerPath);
}

function runExplorerLiveUiTests(): void {
  const config = getConfig();
  if (!ensureExplorerPath(config.explorerPath)) {
    return;
  }

  runInTerminal(
    "Database explorer live UI tests",
    "npm run test:ui:live",
    config.explorerPath,
  );
}

async function probePython(): Promise<Record<string, string>> {
  const config = getConfig();
  const code = `
import importlib
import json

data = {}
for name in ("gemstone_py", "gemstone_py_native"):
    try:
        module = importlib.import_module(name)
        data[name] = getattr(module, "__version__", "installed")
    except Exception as exc:
        data[name] = "not installed: " + exc.__class__.__name__

try:
    from gemstone_py import _gci
    data["gci_backend"] = getattr(_gci, "IMPLEMENTATION", "unknown")
except Exception as exc:
    data["gci_backend"] = "error: " + exc.__class__.__name__ + ": " + str(exc)

print(json.dumps(data, sort_keys=True))
`;

  try {
    const result = await execFileAsync(config.pythonPath, ["-c", code], {
      cwd: config.repoPath,
      env: buildEnv(config),
      timeout: 10000,
    });
    return JSON.parse(result.stdout.trim()) as Record<string, string>;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return {
      gemstone_py: "probe failed",
      gemstone_py_native: "probe failed",
      gci_backend: message,
    };
  }
}

function status(candidate: string): string {
  return pathExists(candidate) ? "exists" : "missing";
}

function ensureExplorerPath(explorerPath: string): boolean {
  if (!explorerPath) {
    void vscode.window.showWarningMessage(
      "Set gemstonePy.explorerPath before launching the database explorer.",
    );
    return false;
  }

  if (!pathExists(explorerPath)) {
    void vscode.window.showWarningMessage(
      `Database explorer path does not exist: ${explorerPath}`,
    );
    return false;
  }

  return true;
}

function ensureExplorerCredentials(env: Record<string, string>): boolean {
  const missing = ["GS_USERNAME", "GS_PASSWORD"].filter(
    (key) => !env[key] || env[key].trim().length === 0,
  );
  if (missing.length === 0) {
    return true;
  }

  void vscode.window.showWarningMessage(
    `Set ${missing.map((key) => `gemstonePy.env.${key}`).join(" and ")} before launching the database explorer.`,
  );
  return false;
}
