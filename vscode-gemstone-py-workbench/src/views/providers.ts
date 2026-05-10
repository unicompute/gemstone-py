import * as fs from "fs";
import * as vscode from "vscode";
import { getConfig, maskEnvValue, pathExists } from "../config";

export class WorkbenchTreeItem {
  public readonly children: WorkbenchTreeItem[];

  public constructor(
    public readonly label: string,
    public readonly options: {
      command?: string;
      description?: string;
      tooltip?: string;
      icon?: string;
      contextValue?: string;
      children?: WorkbenchTreeItem[];
    } = {},
  ) {
    this.children = options.children ?? [];
  }
}

export class WorkbenchTreeProvider
  implements vscode.TreeDataProvider<WorkbenchTreeItem>
{
  private readonly onDidChangeTreeDataEmitter =
    new vscode.EventEmitter<WorkbenchTreeItem | undefined>();

  public readonly onDidChangeTreeData = this.onDidChangeTreeDataEmitter.event;

  public constructor(private readonly itemFactory: () => WorkbenchTreeItem[]) {}

  public refresh(): void {
    this.onDidChangeTreeDataEmitter.fire(undefined);
  }

  public getTreeItem(item: WorkbenchTreeItem): vscode.TreeItem {
    const hasChildren = item.children.length > 0;
    const treeItem = new vscode.TreeItem(
      item.label,
      hasChildren
        ? vscode.TreeItemCollapsibleState.Expanded
        : vscode.TreeItemCollapsibleState.None,
    );
    treeItem.description = item.options.description;
    treeItem.tooltip = item.options.tooltip ?? item.options.description;
    treeItem.contextValue = item.options.contextValue;
    treeItem.iconPath = new vscode.ThemeIcon(item.options.icon ?? "circle-outline");

    if (item.options.command) {
      treeItem.command = {
        command: item.options.command,
        title: item.label,
      };
    }

    return treeItem;
  }

  public getChildren(item?: WorkbenchTreeItem): WorkbenchTreeItem[] {
    return item ? item.children : this.itemFactory();
  }
}

export function createExamplesProvider(): WorkbenchTreeProvider {
  return new WorkbenchTreeProvider(() => [
    commandItem("Grand tour", "gemstonePy.runGrandTour", "examples.example", "play"),
    commandItem(
      "Hello GemStone",
      "gemstonePy.runHelloGemstone",
      "examples.hello_gemstone",
      "play",
    ),
    commandItem(
      "Smalltalk demo",
      "gemstonePy.runSmalltalkDemo",
      "examples.misc.smalltalk_demo",
      "play",
    ),
    commandItem(
      "Async session/root/collection",
      "gemstonePy.runAsyncExample",
      "examples.async_features.session_root_and_collection",
      "play",
    ),
    commandItem(
      "Typed OOPs and queries",
      "gemstonePy.runTypedExample",
      "examples.typed_access.typed_oops_and_queries",
      "play",
    ),
    commandItem(
      "Managed lifetime handles",
      "gemstonePy.runLifetimeExample",
      "examples.lifetime.managed_oop_handles",
      "play",
    ),
    commandItem(
      "Native backend check",
      "gemstonePy.checkNativeBackend",
      "examples.native_backend.check_backend",
      "pulse",
    ),
    commandItem(
      "FastAPI example",
      "gemstonePy.runFastApiExample",
      "examples.fastapi.app:app",
      "server-process",
    ),
  ]);
}

export function createEnvironmentProvider(): WorkbenchTreeProvider {
  return new WorkbenchTreeProvider(() => {
    const config = getConfig();
    const envChildren = Object.entries(config.env).map(([key, value]) => {
      const description = value ? maskEnvValue(key, value) : "missing";
      return new WorkbenchTreeItem(key, {
        description,
        icon: value ? "check" : "warning",
      });
    });

    const gsLib = config.env.GS_LIB;
    const gsLibPath = config.env.GS_LIB_PATH;

    return [
      new WorkbenchTreeItem("Python", {
        description: config.pythonPath,
        icon: "symbol-method",
      }),
      new WorkbenchTreeItem("gemstone-py repo", {
        description: existsDescription(config.repoPath),
        tooltip: config.repoPath,
        icon: pathExists(config.repoPath) ? "repo" : "warning",
      }),
      new WorkbenchTreeItem("Database explorer", {
        description: existsDescription(config.explorerPath),
        tooltip: config.explorerPath,
        icon: pathExists(config.explorerPath) ? "browser" : "warning",
      }),
      new WorkbenchTreeItem("GS_LIB", {
        description: gsLib ? existsDescription(gsLib) : "missing",
        tooltip: gsLib,
        icon: gsLib && pathExists(gsLib) ? "check" : "warning",
      }),
      new WorkbenchTreeItem("GS_LIB_PATH", {
        description: gsLibPath ? existsDescription(gsLibPath) : "not set",
        tooltip: gsLibPath,
        icon: !gsLibPath || pathExists(gsLibPath) ? "check" : "warning",
      }),
      new WorkbenchTreeItem("Configured environment", {
        icon: "settings-gear",
        children: envChildren,
      }),
      commandItem("Show environment report", "gemstonePy.showEnvironment", "", "output"),
      commandItem("Check active GCI backend", "gemstonePy.checkBackend", "", "pulse"),
      commandItem("Copy export script", "gemstonePy.copyEnvScript", "", "copy"),
      commandItem("Open setup guide", "gemstonePy.openSetupGuide", "", "book"),
    ];
  });
}

export function createDocsProvider(): WorkbenchTreeProvider {
  return new WorkbenchTreeProvider(() => [
    commandItem("README", "gemstonePy.openReadme", "README.md", "book"),
    commandItem("Setup guide", "gemstonePy.openSetupGuide", "docs/setup-guide.md", "book"),
    commandItem("User manual", "gemstonePy.openUserManual", "docs/user-manual.md", "book"),
    commandItem(
      "Examples guide",
      "gemstonePy.openExamplesGuide",
      "docs/examples-guide.md",
      "book",
    ),
    commandItem("Medium article", "gemstonePy.openMediumArticle", "docs/medium-article.md", "book"),
    commandItem(
      "Medium article PDF",
      "gemstonePy.openMediumArticlePdf",
      "docs/pdf/medium-article.pdf",
      "file-pdf",
    ),
    commandItem("Rebuild documentation PDFs", "gemstonePy.rebuildDocsPdf", "", "tools"),
  ]);
}

export function createMaintainerProvider(): WorkbenchTreeProvider {
  return new WorkbenchTreeProvider(() => [
    commandItem("Run CI checks", "gemstonePy.runCiChecks", "scripts/run_ci_checks.sh", "beaker"),
    commandItem("Run live checks", "gemstonePy.runLiveChecks", "scripts/run_live_checks.sh", "radio-tower"),
    commandItem("Run benchmarks", "gemstonePy.runBenchmarks", "scripts/run_benchmarks.sh", "dashboard"),
    commandItem("Run native checks", "gemstonePy.runNativeChecks", "scripts/run_native_checks.sh", "rocket"),
  ]);
}

export function createIdeProvider(): WorkbenchTreeProvider {
  return new WorkbenchTreeProvider(() => {
    const config = getConfig();
    const explorerUrl = `http://${config.explorerHost}:${config.explorerPort}/`;

    return [
      new WorkbenchTreeItem("Python Database Explorer", {
        icon: "browser",
        children: [
          commandItem(
            "Launch explorer",
            "gemstonePy.launchDatabaseExplorer",
            config.explorerPath,
            "debug-start",
          ),
          commandItem("Open explorer", "gemstonePy.openDatabaseExplorer", explorerUrl, "link-external"),
          commandItem(
            "Run Python tests",
            "gemstonePy.runDatabaseExplorerTests",
            "pytest",
            "beaker",
          ),
          commandItem(
            "Run UI tests",
            "gemstonePy.runDatabaseExplorerUiTests",
            "npm run test:ui",
            "beaker",
          ),
          commandItem(
            "Run live UI tests",
            "gemstonePy.runDatabaseExplorerLiveUiTests",
            "npm run test:ui:live",
            "radio-tower",
          ),
          commandItem(
            "Open repository",
            "gemstonePy.openDatabaseExplorerRepository",
            "github.com/unicompute/python-gemstone-database-explorer",
            "link-external",
          ),
        ],
      }),
      new WorkbenchTreeItem("Jasper", {
        icon: "symbol-class",
        children: [
          commandItem(
            "Open Jasper",
            "gemstonePy.openJasper",
            "GemStone sidebar",
            "symbol-class",
          ),
          commandItem(
            "Use Jasper for Smalltalk IDE work",
            "gemstonePy.openJasper",
            "browser, inspector, debugger, SUnit",
            "symbol-method",
          ),
          commandItem(
            "Open Jasper repository",
            "gemstonePy.openJasperRepository",
            "github.com/jgfoster/Jasper",
            "link-external",
          ),
        ],
      }),
    ];
  });
}

function commandItem(
  label: string,
  command: string,
  description: string,
  icon: string,
): WorkbenchTreeItem {
  return new WorkbenchTreeItem(label, {
    command,
    description,
    icon,
    tooltip: description,
  });
}

function existsDescription(candidate: string): string {
  if (!candidate) {
    return "missing";
  }
  return fs.existsSync(candidate) ? "exists" : "missing";
}
