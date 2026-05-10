import * as vscode from "vscode";
import { registerCommands } from "./commands/actions";
import {
  WorkbenchTreeProvider,
  createDocsProvider,
  createEnvironmentProvider,
  createExamplesProvider,
  createIdeProvider,
  createMaintainerProvider,
} from "./views/providers";

export function activate(context: vscode.ExtensionContext): void {
  const providers: Array<[string, WorkbenchTreeProvider]> = [
    ["gemstonePy.examplesView", createExamplesProvider()],
    ["gemstonePy.environmentView", createEnvironmentProvider()],
    ["gemstonePy.docsView", createDocsProvider()],
    ["gemstonePy.maintainerView", createMaintainerProvider()],
    ["gemstonePy.ideView", createIdeProvider()],
  ];

  for (const [viewId, provider] of providers) {
    context.subscriptions.push(vscode.window.registerTreeDataProvider(viewId, provider));
  }

  registerCommands(
    context,
    providers.map(([, provider]) => provider),
  );
}

export function deactivate(): void {
  // Nothing to dispose beyond subscriptions registered in activate().
}

