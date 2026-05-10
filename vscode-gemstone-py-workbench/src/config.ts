import * as fs from "fs";
import * as path from "path";
import * as vscode from "vscode";

export type EnvMap = Record<string, string>;

export interface GemStonePyConfig {
  pythonPath: string;
  repoPath: string;
  explorerPath: string;
  explorerHost: string;
  explorerPort: number;
  env: EnvMap;
}

export function getConfig(): GemStonePyConfig {
  const configuration = vscode.workspace.getConfiguration("gemstonePy");
  const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  const repoPath = readString(configuration, "repoPath") || workspaceRoot || "";

  return {
    pythonPath: readString(configuration, "pythonPath") || "python3",
    repoPath,
    explorerPath: readString(configuration, "explorerPath") || "",
    explorerHost: readString(configuration, "explorerHost") || "127.0.0.1",
    explorerPort: readNumber(configuration, "explorerPort") || 9292,
    env: readEnv(configuration.get("env")),
  };
}

export function buildEnv(
  config: GemStonePyConfig,
  extra: EnvMap = {},
): NodeJS.ProcessEnv {
  return {
    ...process.env,
    ...dropEmptyValues(config.env),
    ...dropEmptyValues(extra),
  };
}

export function repoFile(config: GemStonePyConfig, relativePath: string): string {
  return path.join(config.repoPath, relativePath);
}

export function explorerPython(config: GemStonePyConfig): string {
  if (!config.explorerPath) {
    return config.pythonPath;
  }

  const executable = process.platform === "win32" ? "python.exe" : "python";
  const localPython = path.join(config.explorerPath, ".venv", "bin", executable);
  const windowsLocalPython = path.join(
    config.explorerPath,
    ".venv",
    "Scripts",
    executable,
  );

  if (pathExists(localPython)) {
    return localPython;
  }
  if (pathExists(windowsLocalPython)) {
    return windowsLocalPython;
  }
  return config.pythonPath;
}

export function pathExists(candidate: string): boolean {
  if (!candidate) {
    return false;
  }
  return fs.existsSync(candidate);
}

export function shellQuote(value: string): string {
  if (/^[A-Za-z0-9_./:@%+=,-]+$/.test(value)) {
    return value;
  }
  return `'${value.replace(/'/g, "'\\''")}'`;
}

export function maskEnvValue(key: string, value: string): string {
  if (!value) {
    return "<empty>";
  }
  if (/(PASSWORD|SECRET|TOKEN|KEY)/i.test(key)) {
    return "********";
  }
  return value;
}

export function envExportScript(env: EnvMap): string {
  return Object.entries(env)
    .filter(([, value]) => value.length > 0)
    .map(([key, value]) => `export ${key}=${shellQuote(value)}`)
    .join("\n");
}

function readString(
  configuration: vscode.WorkspaceConfiguration,
  key: string,
): string | undefined {
  const value = configuration.get<unknown>(key);
  return typeof value === "string" ? value.trim() : undefined;
}

function readNumber(
  configuration: vscode.WorkspaceConfiguration,
  key: string,
): number | undefined {
  const value = configuration.get<unknown>(key);
  return typeof value === "number" ? value : undefined;
}

function readEnv(value: unknown): EnvMap {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {};
  }

  const entries = Object.entries(value as Record<string, unknown>)
    .filter(([key]) => key.length > 0)
    .map(([key, item]) => [key, item == null ? "" : String(item)]);

  return Object.fromEntries(entries);
}

function dropEmptyValues(env: EnvMap): EnvMap {
  return Object.fromEntries(
    Object.entries(env).filter(([, value]) => value.length > 0),
  );
}
