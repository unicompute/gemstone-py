import * as vscode from "vscode";
import { EnvMap, buildEnv, getConfig, shellQuote } from "../config";

export function runInTerminal(
  title: string,
  command: string,
  cwd: string,
  extraEnv: EnvMap = {},
): void {
  const config = getConfig();
  const terminal = vscode.window.createTerminal({
    name: `GemStone: ${title}`,
    cwd: cwd || undefined,
    env: buildEnv(config, extraEnv),
  });
  terminal.show(true);
  terminal.sendText(command);
}

export function runProcessInTerminal(
  title: string,
  shellPath: string,
  shellArgs: string[],
  cwd: string,
  extraEnv: EnvMap = {},
): void {
  const config = getConfig();
  const terminal = vscode.window.createTerminal({
    name: `GemStone: ${title}`,
    cwd: cwd || undefined,
    env: buildEnv(config, extraEnv),
    shellPath,
    shellArgs,
  });
  terminal.show(true);
}

export function runRepoPythonModule(
  title: string,
  moduleName: string,
  args: string[] = [],
): void {
  const config = getConfig();
  const command = [
    shellQuote(config.pythonPath),
    "-m",
    moduleName,
    ...args.map(shellQuote),
  ].join(" ");
  runInTerminal(title, command, config.repoPath);
}

export function runRepoScript(
  title: string,
  scriptPath: string,
  extraEnv: EnvMap = {},
): void {
  const config = getConfig();
  runInTerminal(title, shellQuote(scriptPath), config.repoPath, extraEnv);
}
