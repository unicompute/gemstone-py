import { execFile } from "child_process";
import * as fs from "fs";
import * as http from "http";
import * as https from "https";
import * as path from "path";
import { promisify } from "util";
import * as vscode from "vscode";
import { buildEnv, getConfig, pathExists } from "../config";
import { runRepoPythonModule } from "./terminal";

const execFileAsync = promisify(execFile);

const DEFAULT_CODEGEN_MODULE = "examples.typed_access.codegen_demo.models";
const DEFAULT_CODEGEN_OUTPUT = "examples/typed_access/codegen_demo/generated";
const DEFAULT_MAPPING_PATH = "codegen-workbench.json";

interface CodegenExplorerMessage {
  id?: number;
  command: string;
  payload?: unknown;
}

interface CodegenExplorerClassSelection {
  dictionary: string;
  className: string;
  protocolName?: string;
  fields?: string[];
  methods?: CodegenExplorerMethodSelection[];
  classMethods?: CodegenExplorerMethodSelection[];
  instanceMethods?: string[];
}

interface CodegenExplorerMethodSelection {
  selector: string;
  pythonName?: string;
  argNames?: string[];
  returnAnnotation?: string;
}

interface CodegenMappingPayload {
  codegenModule?: string;
  codegenOutput?: string;
  mappingPath?: string;
  moduleName?: string;
  async?: boolean;
  classes?: CodegenExplorerClassSelection[];
}

interface GeneratedPreviewFile {
  path: string;
  protocolName: string;
  className: string;
  source: string;
  warnings: string[];
}

interface GeneratedDiffFile {
  path: string;
  status: "added" | "changed" | "unchanged" | "missing";
  diff: string;
}

export function openCodegenExplorer(): string {
  const config = getConfig();
  const explorerUrl = `http://${config.explorerHost}:${config.explorerPort}/`;
  const panel = vscode.window.createWebviewPanel(
    "gemstonePyCodegenExplorer",
    "GemStone Codegen Explorer",
    vscode.ViewColumn.One,
    {
      enableScripts: true,
      retainContextWhenHidden: true,
    },
  );

  panel.webview.html = codegenExplorerHtml();
  panel.webview.onDidReceiveMessage((message: CodegenExplorerMessage) => {
    void handleCodegenExplorerMessage(panel, explorerUrl, message);
  });
  return explorerUrl;
}

async function handleCodegenExplorerMessage(
  panel: vscode.WebviewPanel,
  explorerUrl: string,
  message: CodegenExplorerMessage,
): Promise<void> {
  const id = message.id;
  try {
    const result = await handleCodegenExplorerCommand(explorerUrl, message);
    await panel.webview.postMessage({ replyTo: id, ok: true, result });
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    await panel.webview.postMessage({ replyTo: id, ok: false, error: detail });
  }
}

async function handleCodegenExplorerCommand(
  explorerUrl: string,
  message: CodegenExplorerMessage,
): Promise<unknown> {
  const payload = asPayload(message.payload);
  switch (message.command) {
    case "getConfig":
      return currentCodegenExplorerConfig(explorerUrl);
    case "explorerGet":
      return explorerGet(explorerUrl, readString(payload, "path"));
    case "explorerPost":
      return explorerPost(explorerUrl, readString(payload, "path"), payload.body);
    case "launchExplorer":
      return vscode.commands.executeCommand("gemstonePy.launchDatabaseExplorer");
    case "openExplorer":
      return vscode.commands.executeCommand("gemstonePy.openDatabaseExplorer");
    case "openDocs":
      return vscode.commands.executeCommand("gemstonePy.openCodegenDocs");
    case "runCheck":
      runCodegenCheck(
        readString(payload, "codegenModule") || DEFAULT_CODEGEN_MODULE,
        readString(payload, "codegenOutput") || DEFAULT_CODEGEN_OUTPUT,
      );
      return { started: true };
    case "generateWrappers":
      generateCodegenWrappers(
        readString(payload, "codegenModule") || DEFAULT_CODEGEN_MODULE,
        readString(payload, "codegenOutput") || DEFAULT_CODEGEN_OUTPUT,
      );
      return { started: true };
    case "runDemo":
      return vscode.commands.executeCommand("gemstonePy.runCodegenFastApiDemo");
    case "loadMapping":
      return loadMapping(readString(payload, "mappingPath") || DEFAULT_MAPPING_PATH);
    case "saveMapping":
      return saveMapping(payload);
    case "previewGenerated":
      return previewGenerated(
        readString(payload, "codegenModule") || DEFAULT_CODEGEN_MODULE,
      );
    case "diffGenerated":
      return diffGenerated(
        readString(payload, "codegenModule") || DEFAULT_CODEGEN_MODULE,
        readString(payload, "codegenOutput") || DEFAULT_CODEGEN_OUTPUT,
      );
    case "diffPreviewFiles":
      return diffPreviewFiles(
        payload.files,
        readString(payload, "codegenOutput") || DEFAULT_CODEGEN_OUTPUT,
      );
    case "testSelected":
      return testSelected(payload);
    default:
      throw new Error(`unsupported Codegen Explorer command: ${message.command}`);
  }
}

function currentCodegenExplorerConfig(explorerUrl: string): Record<string, unknown> {
  const config = getConfig();
  const configuration = vscode.workspace.getConfiguration("gemstonePy");
  return {
    explorerUrl,
    repoPath: config.repoPath,
    codegenModule:
      readWorkspaceString(configuration, "codegenModule") || DEFAULT_CODEGEN_MODULE,
    codegenOutput:
      readWorkspaceString(configuration, "codegenOutput") || DEFAULT_CODEGEN_OUTPUT,
    mappingPath:
      readWorkspaceString(configuration, "codegenMappingPath") || DEFAULT_MAPPING_PATH,
  };
}

function readWorkspaceString(
  configuration: vscode.WorkspaceConfiguration,
  key: string,
): string | undefined {
  const value = configuration.get<unknown>(key);
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function runCodegenCheck(moduleName: string, outputDir: string): void {
  runRepoPythonModule("Codegen check", "gemstone_py.codegen", [
    "--module",
    moduleName,
    "--output",
    outputDir,
    "--check",
  ]);
}

function generateCodegenWrappers(moduleName: string, outputDir: string): void {
  runRepoPythonModule("Generate codegen wrappers", "gemstone_py.codegen", [
    "--module",
    moduleName,
    "--output",
    outputDir,
    "--clean",
  ]);
}

async function explorerGet(explorerUrl: string, requestPath: string): Promise<unknown> {
  if (!requestPath.startsWith("/")) {
    throw new Error(`explorer path must start with /: ${requestPath}`);
  }
  const url = new URL(requestPath, explorerUrl);
  return requestJson(url);
}

async function explorerPost(
  explorerUrl: string,
  requestPath: string,
  body: unknown,
): Promise<unknown> {
  if (!requestPath.startsWith("/")) {
    throw new Error(`explorer path must start with /: ${requestPath}`);
  }
  const url = new URL(requestPath, explorerUrl);
  return requestJson(url, { method: "POST", body });
}

function requestJson(
  url: URL,
  options: { method?: "GET" | "POST"; body?: unknown } = {},
): Promise<unknown> {
  const client = url.protocol === "https:" ? https : http;
  const method = options.method || "GET";
  const encodedBody =
    method === "POST" ? JSON.stringify(options.body ?? {}) : undefined;
  return new Promise((resolve, reject) => {
    const request = client.request(
      url,
      {
        method,
        timeout: 10000,
        headers: {
          Accept: "application/json",
          ...(encodedBody
            ? {
                "Content-Type": "application/json",
                "Content-Length": Buffer.byteLength(encodedBody).toString(),
              }
            : {}),
        },
      },
      (response) => {
        let body = "";
        response.setEncoding("utf8");
        response.on("data", (chunk: string) => {
          body += chunk;
        });
        response.on("end", () => {
          if ((response.statusCode ?? 500) >= 400) {
            reject(new Error(`explorer returned HTTP ${response.statusCode}: ${body}`));
            return;
          }
          try {
            resolve(JSON.parse(body));
          } catch (error) {
            reject(
              new Error(
                `explorer returned non-JSON response from ${url.pathname}: ${
                  error instanceof Error ? error.message : String(error)
                }`,
              ),
            );
          }
        });
      },
    );
    request.on("timeout", () => {
      request.destroy(new Error(`timed out fetching ${url.toString()}`));
    });
    request.on("error", reject);
    if (encodedBody) {
      request.write(encodedBody);
    }
    request.end();
  });
}

async function loadMapping(mappingPath: string): Promise<Record<string, unknown>> {
  const config = getConfig();
  const fullPath = resolveRepoFile(config.repoPath, mappingPath);
  if (!pathExists(fullPath)) {
    return {
      exists: false,
      path: fullPath,
      mapping: {
        schemaVersion: 1,
        moduleName: DEFAULT_CODEGEN_MODULE,
        codegenOutput: DEFAULT_CODEGEN_OUTPUT,
        classes: [],
      },
    };
  }
  const mapping = JSON.parse(fs.readFileSync(fullPath, "utf8")) as Record<
    string,
    unknown
  >;
  return { exists: true, path: fullPath, mapping };
}

async function saveMapping(payload: Record<string, unknown>): Promise<Record<string, unknown>> {
  const config = getConfig();
  const mappingPayload = normalizeMappingPayload(payload);
  const fullPath = resolveRepoFile(config.repoPath, mappingPayload.mappingPath);
  fs.mkdirSync(path.dirname(fullPath), { recursive: true });
  const mapping = {
    schemaVersion: 1,
    moduleName: mappingPayload.codegenModule,
    async: mappingPayload.async,
    codegenOutput: mappingPayload.codegenOutput,
    classes: mappingPayload.classes,
  };
  fs.writeFileSync(fullPath, `${JSON.stringify(mapping, null, 2)}\n`, "utf8");
  return { path: fullPath, mapping };
}

async function previewGenerated(moduleName: string): Promise<GeneratedPreviewFile[]> {
  const payload = await runPythonJson(
    previewScript(),
    [moduleName],
    20000,
  );
  return payload as GeneratedPreviewFile[];
}

async function diffGenerated(
  moduleName: string,
  outputDir: string,
): Promise<GeneratedDiffFile[]> {
  const config = getConfig();
  const generated = await previewGenerated(moduleName);
  return diffFilesAgainstOutput(generated, config.repoPath, outputDir);
}

async function diffPreviewFiles(
  files: unknown,
  outputDir: string,
): Promise<GeneratedDiffFile[]> {
  const config = getConfig();
  const generated = normalizeGeneratedPreviewFiles(files);
  return diffFilesAgainstOutput(generated, config.repoPath, outputDir);
}

function diffFilesAgainstOutput(
  generated: GeneratedPreviewFile[],
  repoPath: string,
  outputDir: string,
): GeneratedDiffFile[] {
  const outputPath = resolveCodegenOutput(repoPath, outputDir);
  return generated.map((file) => {
    const currentPath = path.join(outputPath, file.path);
    if (!pathExists(currentPath)) {
      return {
        path: file.path,
        status: "added",
        diff: buildUnifiedDiff(file.path, "", file.source),
      };
    }
    const current = fs.readFileSync(currentPath, "utf8");
    if (current === file.source) {
      return { path: file.path, status: "unchanged", diff: "" };
    }
    return {
      path: file.path,
      status: "changed",
      diff: buildUnifiedDiff(file.path, current, file.source),
    };
  });
}

function normalizeGeneratedPreviewFiles(value: unknown): GeneratedPreviewFile[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .filter((item) => item && typeof item === "object")
    .map((item) => {
      const raw = item as Record<string, unknown>;
      return {
        path: readString(raw, "path"),
        protocolName: readString(raw, "protocolName"),
        className: readString(raw, "className"),
        source: readString(raw, "source"),
        warnings: readStringArray(raw.warnings),
      };
    })
    .filter((item) => item.path.length > 0);
}

async function testSelected(payload: Record<string, unknown>): Promise<Record<string, unknown>> {
  const mappingPayload = normalizeMappingPayload(payload);
  const probeClasses = mappingPayload.classes.map((item) => ({
    dictionary: item.dictionary,
    className: item.className,
    instanceMethods: [
      ...new Set([
        ...(item.fields || []),
        ...methodSelectors(item.methods || []),
        ...(item.instanceMethods || []),
      ]),
    ],
    classMethods: methodSelectors(item.classMethods || []),
  }));
  return (await runPythonJson(
    testSelectedScript(),
    [
      mappingPayload.codegenModule,
      mappingPayload.codegenOutput,
      JSON.stringify(probeClasses),
    ],
    20000,
  )) as Record<string, unknown>;
}

function methodSelectors(methods: CodegenExplorerMethodSelection[]): string[] {
  return methods.map((method) => method.selector).filter((selector) => selector.length > 0);
}

async function runPythonJson(
  code: string,
  args: string[],
  timeout: number,
): Promise<unknown> {
  const config = getConfig();
  const result = await execFileAsync(config.pythonPath, ["-c", code, ...args], {
    cwd: config.repoPath,
    env: buildEnv(config),
    timeout,
    maxBuffer: 20 * 1024 * 1024,
  });
  return JSON.parse(lastJsonLine(result.stdout));
}

function previewScript(): string {
  return String.raw`
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from gemstone_py.codegen import generate_package

module_name = sys.argv[1]
with TemporaryDirectory() as tmp:
    files = generate_package(module_name, Path(tmp))
    result = []
    for item in files:
        result.append({
            "path": Path(item.path).relative_to(tmp).as_posix(),
            "protocolName": item.protocol_name,
            "className": item.class_name,
            "source": item.source,
            "warnings": list(item.warnings),
        })
print(json.dumps(result, sort_keys=True))
`;
}

function testSelectedScript(): string {
  return String.raw`
import importlib
import inspect
import json
import sys
from pathlib import Path

from gemstone_py import GemStoneConfig, GemStoneSession, TransactionPolicy

module_name = sys.argv[1]
output_dir = sys.argv[2]
classes = json.loads(sys.argv[3])

def st_literal(value):
    return "'" + str(value).replace("'", "''") + "'"

def behavior_expr(item, meta=False):
    dictionary = item.get("dictionary") or ""
    class_name = item.get("className") or ""
    if dictionary:
        base = "((System myUserProfile symbolList objectNamed: " + st_literal(dictionary) + " asSymbol) at: " + st_literal(class_name) + " asSymbol ifAbsent: [nil])"
    else:
        base = "(Smalltalk at: " + st_literal(class_name) + " asSymbol ifAbsent: [nil])"
    if meta:
        return "(" + base + " ifNil: [nil] ifNotNil: [:cls | cls class])"
    return base

def has_method_source(item, selector, meta=False):
    return "[ | cls | cls := " + behavior_expr(item, meta) + ". cls notNil and: [cls selectors includes: " + st_literal(selector) + " asSymbol] ] value"

def output_module_name(output):
    rel = Path(output)
    if rel.is_absolute():
        rel = rel.relative_to(Path.cwd())
    return ".".join(rel.parts)

generated_classes = {}
try:
    generated_module = importlib.import_module(output_module_name(output_dir))
    for name in dir(generated_module):
        obj = getattr(generated_module, name)
        if inspect.isclass(obj):
            gs_name = getattr(obj, "__gemstone_class_name__", None)
            if gs_name:
                generated_classes.setdefault(gs_name, []).append(name)
except Exception as exc:
    generated_module = None
    generated_import_error = exc.__class__.__name__ + ": " + str(exc)
else:
    generated_import_error = ""

rows = []
try:
    config = GemStoneConfig.from_env()
    with GemStoneSession(config=config, transaction_policy=TransactionPolicy.ABORT_ON_EXIT) as session:
        for item in classes:
            class_name = item.get("className", "")
            live = bool(session.eval("[ | cls | cls := " + behavior_expr(item, False) + ". cls notNil ] value"))
            instance_methods = []
            for selector in item.get("instanceMethods", []):
                instance_methods.append({
                    "selector": selector,
                    "exists": bool(session.eval(has_method_source(item, selector, False))),
                })
            class_methods = []
            for selector in item.get("classMethods", []):
                class_methods.append({
                    "selector": selector,
                    "exists": bool(session.eval(has_method_source(item, selector, True))),
                })
            rows.append({
                "dictionary": item.get("dictionary", ""),
                "className": class_name,
                "liveClassExists": live,
                "generatedWrappers": generated_classes.get(class_name, []),
                "instanceMethods": instance_methods,
                "classMethods": class_methods,
            })
    result = {"ok": True, "generatedImportError": generated_import_error, "rows": rows}
except Exception as exc:
    result = {"ok": False, "error": exc.__class__.__name__ + ": " + str(exc), "generatedImportError": generated_import_error, "rows": rows}
print(json.dumps(result, sort_keys=True))
`;
}

function normalizeMappingPayload(payload: Record<string, unknown>): Required<CodegenMappingPayload> {
  const classesValue = Array.isArray(payload.classes) ? payload.classes : [];
  const classes = classesValue
    .map((item) => normalizeSelection(item))
    .filter((item): item is CodegenExplorerClassSelection => item !== undefined);
  return {
    codegenModule:
      readString(payload, "moduleName") ||
      readString(payload, "codegenModule") ||
      DEFAULT_CODEGEN_MODULE,
    codegenOutput: readString(payload, "codegenOutput") || DEFAULT_CODEGEN_OUTPUT,
    mappingPath: readString(payload, "mappingPath") || DEFAULT_MAPPING_PATH,
    moduleName:
      readString(payload, "moduleName") ||
      readString(payload, "codegenModule") ||
      DEFAULT_CODEGEN_MODULE,
    async: payload.async !== false,
    classes,
  };
}

function normalizeSelection(value: unknown): CodegenExplorerClassSelection | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return undefined;
  }
  const item = value as Record<string, unknown>;
  const className = readString(item, "className");
  if (!className) {
    return undefined;
  }
  return {
    dictionary: readString(item, "dictionary"),
    className,
    protocolName: readString(item, "protocolName") || `${className}Proto`,
    fields: readStringArray(item.fields),
    methods: readMethodSelections(item.methods ?? item.instanceMethods),
    classMethods: readMethodSelections(item.classMethods),
    instanceMethods: readStringArray(item.instanceMethods),
  };
}

function readMethodSelections(value: unknown): CodegenExplorerMethodSelection[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item): CodegenExplorerMethodSelection | undefined => {
      if (typeof item === "string") {
        return { selector: item };
      }
      if (!item || typeof item !== "object") {
        return undefined;
      }
      const raw = item as Record<string, unknown>;
      const selector = readString(raw, "selector");
      if (!selector) {
        return undefined;
      }
      return {
        selector,
        pythonName: readString(raw, "pythonName") || undefined,
        argNames: readStringArray(raw.argNames),
        returnAnnotation: readString(raw, "returnAnnotation") || undefined,
      };
    })
    .filter((item): item is CodegenExplorerMethodSelection => item !== undefined);
}

function readStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is string => typeof item === "string");
}

function asPayload(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function readString(payload: Record<string, unknown>, key: string): string {
  const value = payload[key];
  return typeof value === "string" ? value.trim() : "";
}

function resolveRepoFile(repoPath: string, candidate: string): string {
  const fullPath = path.isAbsolute(candidate)
    ? path.resolve(candidate)
    : path.resolve(repoPath, candidate);
  const root = path.resolve(repoPath);
  if (fullPath !== root && !fullPath.startsWith(root + path.sep)) {
    throw new Error(`path must stay inside gemstone-py checkout: ${candidate}`);
  }
  return fullPath;
}

function resolveCodegenOutput(repoPath: string, outputDir: string): string {
  return path.isAbsolute(outputDir) ? outputDir : path.join(repoPath, outputDir);
}

function buildUnifiedDiff(relativePath: string, current: string, generated: string): string {
  const currentLines = current.split(/\r?\n/);
  const generatedLines = generated.split(/\r?\n/);
  let start = 0;
  while (
    start < currentLines.length &&
    start < generatedLines.length &&
    currentLines[start] === generatedLines[start]
  ) {
    start += 1;
  }

  let currentEnd = currentLines.length - 1;
  let generatedEnd = generatedLines.length - 1;
  while (
    currentEnd >= start &&
    generatedEnd >= start &&
    currentLines[currentEnd] === generatedLines[generatedEnd]
  ) {
    currentEnd -= 1;
    generatedEnd -= 1;
  }

  const contextStart = Math.max(0, start - 3);
  const contextCurrentEnd = Math.min(currentLines.length - 1, currentEnd + 3);
  const contextGeneratedEnd = Math.min(generatedLines.length - 1, generatedEnd + 3);
  const lines = [
    `--- ${relativePath} (current)`,
    `+++ ${relativePath} (generated)`,
    `@@ -${contextStart + 1},${contextCurrentEnd - contextStart + 1} +${
      contextStart + 1
    },${contextGeneratedEnd - contextStart + 1} @@`,
  ];

  for (let index = contextStart; index < start; index += 1) {
    lines.push(` ${currentLines[index]}`);
  }
  for (let index = start; index <= currentEnd; index += 1) {
    lines.push(`-${currentLines[index]}`);
  }
  for (let index = start; index <= generatedEnd; index += 1) {
    lines.push(`+${generatedLines[index]}`);
  }
  for (let index = currentEnd + 1; index <= contextCurrentEnd; index += 1) {
    lines.push(` ${currentLines[index]}`);
  }
  return lines.join("\n");
}

function lastJsonLine(stdout: string): string {
  const lines = stdout
    .trim()
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
  return lines[lines.length - 1] ?? "{}";
}

function codegenExplorerHtml(): string {
  const nonce = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta
    http-equiv="Content-Security-Policy"
    content="default-src 'none'; script-src 'nonce-${nonce}'; style-src 'unsafe-inline';"
  >
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>GemStone Codegen Explorer</title>
  <style>
    :root {
      color-scheme: light dark;
      --gap: 10px;
      --border: var(--vscode-panel-border, #3c3c3c);
      --muted: var(--vscode-descriptionForeground);
      --bg: var(--vscode-editor-background);
      --panel: var(--vscode-sideBar-background);
      --accent: var(--vscode-button-background);
      --accent-fg: var(--vscode-button-foreground);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--vscode-foreground);
      font-family: var(--vscode-font-family);
      font-size: var(--vscode-font-size);
    }
    button, input, select {
      font: inherit;
    }
    button {
      border: 1px solid var(--vscode-button-border, transparent);
      background: var(--accent);
      color: var(--accent-fg);
      min-height: 28px;
      padding: 4px 10px;
      cursor: pointer;
    }
    button.secondary {
      background: var(--vscode-button-secondaryBackground);
      color: var(--vscode-button-secondaryForeground);
    }
    button:disabled {
      opacity: 0.55;
      cursor: default;
    }
    input, select {
      width: 100%;
      min-height: 28px;
      border: 1px solid var(--vscode-input-border, var(--border));
      background: var(--vscode-input-background);
      color: var(--vscode-input-foreground);
      padding: 4px 7px;
    }
    label {
      display: grid;
      gap: 4px;
      min-width: 0;
      color: var(--muted);
    }
    code, pre {
      font-family: var(--vscode-editor-font-family);
      font-size: var(--vscode-editor-font-size);
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: var(--gap);
      min-height: 44px;
      padding: 8px 12px;
      border-bottom: 1px solid var(--border);
      background: var(--panel);
    }
    h1, h2 {
      margin: 0;
      letter-spacing: 0;
    }
    h1 { font-size: 17px; }
    h2 { font-size: 13px; }
    .status {
      color: var(--muted);
      text-align: right;
      min-width: 180px;
    }
    .toolbar {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      padding: 8px 12px;
      border-bottom: 1px solid var(--border);
    }
    .layout {
      display: grid;
      grid-template-columns: minmax(320px, 36%) minmax(420px, 1fr);
      min-height: calc(100vh - 90px);
    }
    .pane {
      min-width: 0;
      padding: 10px 12px;
      border-right: 1px solid var(--border);
    }
    .pane:last-child { border-right: 0; }
    .fields {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
      margin-bottom: 10px;
    }
    .fields.single {
      grid-template-columns: 1fr;
    }
    .list {
      border: 1px solid var(--border);
      min-height: 160px;
      max-height: 280px;
      overflow: auto;
      background: var(--vscode-list-inactiveSelectionBackground, transparent);
    }
    .row {
      display: grid;
      grid-template-columns: 22px minmax(0, 1fr);
      gap: 6px;
      align-items: center;
      min-height: 28px;
      padding: 3px 7px;
      border-bottom: 1px solid color-mix(in srgb, var(--border), transparent 55%);
    }
    .row button {
      background: transparent;
      color: var(--vscode-foreground);
      border: 0;
      min-height: 22px;
      padding: 0;
      text-align: left;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: normal;
      line-height: 1.25;
    }
    .row.active {
      background: var(--vscode-list-activeSelectionBackground);
      color: var(--vscode-list-activeSelectionForeground);
    }
    .section {
      display: grid;
      gap: 8px;
      margin: 0 0 12px;
    }
    .inline {
      display: flex;
      gap: 8px;
      align-items: center;
    }
    .inline label {
      display: flex;
      flex-direction: row;
      align-items: center;
      gap: 6px;
      color: var(--vscode-foreground);
    }
    .inline input[type="checkbox"],
    .row input[type="checkbox"] {
      width: 16px;
      min-height: 16px;
      padding: 0;
    }
    .output-tabs {
      display: flex;
      gap: 6px;
      margin-bottom: 8px;
    }
    .output-tabs button.active {
      outline: 2px solid var(--vscode-focusBorder);
      outline-offset: 1px;
    }
    pre {
      min-height: 320px;
      max-height: calc(100vh - 330px);
      overflow: auto;
      margin: 0;
      padding: 10px;
      border: 1px solid var(--border);
      background: var(--vscode-textCodeBlock-background, var(--panel));
      white-space: pre-wrap;
    }
    .selected-table {
      width: 100%;
      border-collapse: collapse;
      margin-bottom: 10px;
    }
    .selected-table th,
    .selected-table td {
      border-bottom: 1px solid var(--border);
      padding: 5px 6px;
      text-align: left;
      vertical-align: top;
    }
    .muted { color: var(--muted); }
    @media (max-width: 840px) {
      .layout { grid-template-columns: 1fr; }
      .pane { border-right: 0; border-bottom: 1px solid var(--border); }
      .fields { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Codegen Explorer</h1>
    <div id="status" class="status">Starting...</div>
  </header>
  <div class="toolbar">
    <button id="connectBtn">Connect</button>
    <button id="launchBtn" class="secondary">Launch Explorer</button>
    <button id="openExplorerBtn" class="secondary">Open Explorer</button>
    <button id="openDocsBtn" class="secondary">Open Docs</button>
  </div>
  <main class="layout">
    <section class="pane">
      <div class="section">
        <h2>Live Stone Browser</h2>
        <div class="fields">
          <label>Dictionary<select id="dictionarySelect"></select></label>
          <label>Filter Classes<input id="classFilter" placeholder="Class name"></label>
        </div>
        <div id="classList" class="list" aria-label="Classes"></div>
      </div>
      <div class="section">
        <div class="inline">
          <h2>Methods</h2>
          <label><input id="metaToggle" type="checkbox"> class side</label>
        </div>
        <div class="fields">
          <label>Protocol<select id="protocolSelect"></select></label>
          <label>Selected Class<input id="selectedClassName" readonly></label>
        </div>
        <div id="methodList" class="list" aria-label="Methods"></div>
      </div>
      <div class="section">
        <h2>Source</h2>
        <pre id="sourcePreview">Select a class or method.</pre>
      </div>
    </section>
    <section class="pane">
      <div class="section">
        <h2>Codegen Configuration</h2>
        <div class="fields">
          <label>Protocol Module<input id="codegenModule"></label>
          <label>Output Package<input id="codegenOutput"></label>
        </div>
        <div class="fields single">
          <label>Mapping File<input id="mappingPath"></label>
        </div>
        <div class="toolbar" style="padding: 0; border: 0;">
          <button id="previewBtn">Preview Wrappers</button>
          <button id="diffBtn">Diff Output</button>
          <button id="saveBtn">Save Mapping</button>
          <button id="loadBtn" class="secondary">Load Mapping</button>
          <button id="testBtn" class="secondary">Test Live Targets</button>
          <button id="checkBtn" class="secondary">Run Check</button>
          <button id="generateBtn" class="secondary">Generate</button>
          <button id="demoBtn" class="secondary">Run Demo</button>
        </div>
      </div>
      <div class="section">
        <h2>Selected Classes</h2>
        <table class="selected-table">
          <thead>
            <tr><th>Dictionary</th><th>Class</th><th>Instance Methods</th><th>Class Methods</th></tr>
          </thead>
          <tbody id="selectedTable"></tbody>
        </table>
      </div>
      <div class="section">
        <div class="output-tabs">
          <button id="tabPreview" class="secondary active">Preview</button>
          <button id="tabDiff" class="secondary">Diff</button>
          <button id="tabMapping" class="secondary">Mapping</button>
          <button id="tabReport" class="secondary">Report</button>
        </div>
        <pre id="outputPane">Connect to the explorer, select classes, then preview or diff the generated wrappers.</pre>
      </div>
    </section>
  </main>
  <script nonce="${nonce}">
    const vscode = acquireVsCodeApi();
    let nextId = 1;
    const pending = new Map();
    const state = {
      explorerUrl: '',
      dictionaries: [],
      dictionary: '',
      classes: [],
      classFilter: '',
      currentClass: '',
      meta: false,
      protocols: [],
      protocol: '',
      methods: [],
      selected: new Map(),
      lastPreviewFiles: [],
      outputTab: 'preview',
      output: {
        preview: '',
        diff: '',
        mapping: '',
        report: ''
      }
    };

    function request(command, payload) {
      const id = nextId++;
      vscode.postMessage({ id, command, payload: payload || {} });
      return new Promise((resolve, reject) => {
        pending.set(id, { resolve, reject });
        setTimeout(() => {
          if (pending.has(id)) {
            pending.delete(id);
            reject(new Error(command + ' timed out'));
          }
        }, 45000);
      });
    }

    window.addEventListener('message', (event) => {
      const message = event.data || {};
      const item = pending.get(message.replyTo);
      if (!item) {
        return;
      }
      pending.delete(message.replyTo);
      if (message.ok) {
        item.resolve(message.result);
      } else {
        item.reject(new Error(message.error || 'command failed'));
      }
    });

    function payload() {
      const moduleName = document.getElementById('codegenModule').value.trim();
      return {
        moduleName,
        codegenModule: moduleName,
        async: true,
        codegenOutput: document.getElementById('codegenOutput').value.trim(),
        mappingPath: document.getElementById('mappingPath').value.trim(),
        classes: Array.from(state.selected.values())
      };
    }

    function codegenSelectionPayload() {
      const data = payload();
      return {
        schemaVersion: 1,
        moduleName: data.moduleName,
        async: data.async,
        classes: data.classes
      };
    }

    function setStatus(value) {
      document.getElementById('status').textContent = value;
    }

    function setOutput(tab, value) {
      state.output[tab] = value || '';
      state.outputTab = tab;
      renderOutput();
    }

    function renderOutput() {
      for (const tab of ['preview', 'diff', 'mapping', 'report']) {
        document.getElementById('tab' + tab[0].toUpperCase() + tab.slice(1)).classList.toggle('active', state.outputTab === tab);
      }
      document.getElementById('outputPane').textContent = state.output[state.outputTab] || '';
    }

    function escapeHtml(value) {
      return String(value).replace(/[&<>"']/g, (char) => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
      })[char]);
    }

    function keyFor(dictionary, className) {
      return dictionary + '::' + className;
    }

    function ensureSelection(dictionary, className) {
      const key = keyFor(dictionary, className);
      if (!state.selected.has(key)) {
        state.selected.set(key, {
          dictionary,
          className,
          protocolName: className + 'Proto',
          fields: [],
          methods: [],
          classMethods: []
        });
      }
      return state.selected.get(key);
    }

    function renderDictionaries() {
      const select = document.getElementById('dictionarySelect');
      select.innerHTML = state.dictionaries.map((name) =>
        '<option value="' + escapeHtml(name) + '">' + escapeHtml(name) + '</option>'
      ).join('');
      select.value = state.dictionary;
    }

    function renderClasses() {
      const needle = state.classFilter.toLowerCase();
      const rows = state.classes.filter((name) => !needle || name.toLowerCase().includes(needle));
      document.getElementById('classList').innerHTML = rows.map((className) => {
        const checked = state.selected.has(keyFor(state.dictionary, className)) ? ' checked' : '';
        const active = className === state.currentClass ? ' active' : '';
        return '<div class="row' + active + '"><input type="checkbox" data-class-check="' + escapeHtml(className) + '"' + checked + '><button data-class="' + escapeHtml(className) + '">' + escapeHtml(className) + '</button></div>';
      }).join('') || '<div class="row"><span></span><span class="muted">No classes loaded.</span></div>';
    }

    function renderProtocols() {
      const select = document.getElementById('protocolSelect');
      const protocols = ['', ...state.protocols.filter((name) => name)];
      select.innerHTML = protocols.map((name) =>
        '<option value="' + escapeHtml(name) + '">' + escapeHtml(name || 'All protocols') + '</option>'
      ).join('');
      select.value = state.protocol;
    }

    function renderMethods() {
      const current = state.currentClass;
      const selection = current ? state.selected.get(keyFor(state.dictionary, current)) : undefined;
      const selectedMethods = new Set((selection ? (state.meta ? selection.classMethods : selection.methods) : []).map((method) => method.selector));
      const selectedFields = new Set(selection ? selection.fields || [] : []);
      document.getElementById('methodList').innerHTML = state.methods.map((method) => {
        const selector = method.selector || '';
        const checked = selectedMethods.has(selector) || (!state.meta && method.propertyCandidate && selectedFields.has(method.pythonName || selector)) ? ' checked' : '';
        const detail = [method.category, method.pythonName, method.argCount + ' arg' + (method.argCount === 1 ? '' : 's')].filter(Boolean).join(' / ');
        return '<div class="row"><input type="checkbox" data-method-check="' + escapeHtml(selector) + '"' + checked + '><button data-method="' + escapeHtml(selector) + '">' + escapeHtml(selector) + '<br><span class="muted">' + escapeHtml(detail) + '</span></button></div>';
      }).join('') || '<div class="row"><span></span><span class="muted">No methods loaded.</span></div>';
    }

    function renderSelected() {
      const rows = Array.from(state.selected.values());
      document.getElementById('selectedTable').innerHTML = rows.map((item) =>
        '<tr><td>' + escapeHtml(item.dictionary) + '</td><td>' + escapeHtml(item.className) + '</td><td>' + escapeHtml([...(item.fields || []), ...(item.methods || []).map((method) => method.selector)].join(', ')) + '</td><td>' + escapeHtml((item.classMethods || []).map((method) => method.selector).join(', ')) + '</td></tr>'
      ).join('') || '<tr><td colspan="4" class="muted">No classes selected.</td></tr>';
      setOutput('mapping', JSON.stringify(payload(), null, 2));
    }

    function findCurrentMethod(selector) {
      selector = String(selector || '');
      return state.methods.find((method) => method.selector === selector) || { selector, pythonName: selector, argCount: selector.split(':').length - 1 };
    }

    function methodArgNames(method) {
      const count = Math.max(0, Number(method.argCount || 0));
      return Array.from({ length: count }, (_, index) => 'arg' + (index + 1));
    }

    function toMethodSelection(method) {
      return {
        selector: method.selector,
        pythonName: method.pythonName || method.selector,
        argNames: methodArgNames(method),
        returnAnnotation: 'Any'
      };
    }

    function removeMethodSelection(list, selector) {
      const index = list.findIndex((method) => method.selector === selector);
      if (index !== -1) {
        list.splice(index, 1);
      }
    }

    function applyMapping(mapping) {
      const classes = Array.isArray(mapping.classes) ? mapping.classes : [];
      state.selected = new Map();
      for (const item of classes) {
        if (!item || !item.className) {
          continue;
        }
        const normalized = {
          dictionary: item.dictionary || '',
          className: item.className,
          protocolName: item.protocolName || item.className + 'Proto',
          fields: Array.isArray(item.fields) ? item.fields : [],
          methods: normalizeMethodList(item.methods || item.instanceMethods),
          classMethods: normalizeMethodList(item.classMethods)
        };
        state.selected.set(keyFor(normalized.dictionary, normalized.className), normalized);
      }
    }

    function normalizeMethodList(value) {
      return Array.isArray(value) ? value.map((item) => {
        if (typeof item === 'string') {
          return { selector: item, pythonName: item, argNames: [], returnAnnotation: 'Any' };
        }
        return {
          selector: item.selector || '',
          pythonName: item.pythonName || item.selector || '',
          argNames: Array.isArray(item.argNames) ? item.argNames : [],
          returnAnnotation: item.returnAnnotation || 'Any'
        };
      }).filter((item) => item.selector) : [];
    }

    async function explorerGet(path) {
      const data = await request('explorerGet', { path });
      if (data && data.success === false) {
        throw new Error(data.exception || 'explorer request failed');
      }
      return data || {};
    }

    async function connect() {
      setStatus('Connecting to explorer...');
      const data = await explorerGet('/codegen/dictionaries');
      state.dictionaries = data.dictionaries || [];
      state.dictionary = state.dictionaries[0] || '';
      renderDictionaries();
      await loadClasses();
      setStatus('Connected to ' + state.explorerUrl);
    }

    async function loadClasses() {
      if (!state.dictionary) {
        return;
      }
      setStatus('Loading classes...');
      const data = await explorerGet('/codegen/classes?dictionary=' + encodeURIComponent(state.dictionary));
      state.classes = (data.classes || []).map((item) => item.className || item).filter(Boolean);
      state.currentClass = state.classes[0] || '';
      renderClasses();
      await loadClassDetails();
    }

    async function loadClassDetails() {
      document.getElementById('selectedClassName').value = state.currentClass || '';
      if (!state.currentClass) {
        state.protocols = [];
        state.methods = [];
        renderProtocols();
        renderMethods();
        document.getElementById('sourcePreview').textContent = 'Select a class.';
        return;
      }
      const meta = state.meta ? '1' : '0';
      const base = 'class=' + encodeURIComponent(state.currentClass) + '&dictionary=' + encodeURIComponent(state.dictionary) + '&meta=' + meta;
      const categories = await explorerGet('/codegen/protocols?' + base);
      state.protocols = categories.protocols || [];
      state.protocol = state.protocols.includes(state.protocol) ? state.protocol : '';
      renderProtocols();
      const methods = await explorerGet('/codegen/methods?' + base + '&protocol=' + encodeURIComponent(state.protocol));
      state.methods = methods.methods || [];
      renderMethods();
      document.getElementById('sourcePreview').textContent = 'Select a selector.';
    }

    async function showMethodSource(selector) {
      if (!state.currentClass) {
        return;
      }
      const meta = state.meta ? '1' : '0';
      const query = 'class=' + encodeURIComponent(state.currentClass) + '&dictionary=' + encodeURIComponent(state.dictionary) + '&meta=' + meta + '&selector=' + encodeURIComponent(selector);
      const source = await explorerGet('/codegen/source?' + query);
      document.getElementById('sourcePreview').textContent = source.source || '';
    }

    async function withBusy(label, action) {
      try {
        setStatus(label);
        await action();
      } catch (error) {
        setStatus('Error');
        setOutput('report', error.message || String(error));
      }
    }

    function formatPreview(files) {
      if (!files.length) {
        return 'No generated files.';
      }
      return files.map((file) =>
        '# ' + file.path + '\\n' + ((file.warnings || []).length ? '# warnings: ' + file.warnings.join('; ') + '\\n' : '') + (file.source || '')
      ).join('\\n\\n');
    }

    function formatDiff(files) {
      if (!files.length) {
        return 'No generated files.';
      }
      return files.map((file) => {
        if (file.status === 'unchanged') {
          return '# ' + file.path + ': unchanged';
        }
        return '# ' + file.path + ': ' + file.status + '\\n' + file.diff;
      }).join('\\n\\n');
    }

    function formatReport(result) {
      if (!result.ok) {
        return 'Live target test failed: ' + result.error + '\\nGenerated import: ' + (result.generatedImportError || 'ok');
      }
      const lines = ['Live target test', 'Generated import: ' + (result.generatedImportError || 'ok'), ''];
      for (const row of result.rows || []) {
        lines.push(row.dictionary + '::' + row.className);
        lines.push('  live class: ' + (row.liveClassExists ? 'ok' : 'missing'));
        lines.push('  generated wrappers: ' + (row.generatedWrappers && row.generatedWrappers.length ? row.generatedWrappers.join(', ') : 'missing'));
        for (const method of row.instanceMethods || []) {
          lines.push('  instance ' + method.selector + ': ' + (method.exists ? 'ok' : 'missing'));
        }
        for (const method of row.classMethods || []) {
          lines.push('  class ' + method.selector + ': ' + (method.exists ? 'ok' : 'missing'));
        }
      }
      return lines.join('\\n');
    }

    document.addEventListener('click', (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }
      const className = target.getAttribute('data-class');
      if (className) {
        state.currentClass = className;
        renderClasses();
        void withBusy('Loading ' + className + '...', loadClassDetails);
        return;
      }
      const selector = target.getAttribute('data-method');
      if (selector) {
        void withBusy('Loading source...', () => showMethodSource(selector));
      }
    });

    document.addEventListener('change', (event) => {
      const target = event.target;
      if (!(target instanceof HTMLInputElement || target instanceof HTMLSelectElement)) {
        return;
      }
      if (target.id === 'dictionarySelect') {
        state.dictionary = target.value;
        void withBusy('Loading dictionary...', loadClasses);
      } else if (target.id === 'protocolSelect') {
        state.protocol = target.value;
        void withBusy('Loading protocol...', loadClassDetails);
      } else if (target.id === 'metaToggle') {
        state.meta = target.checked;
        void withBusy('Loading side...', loadClassDetails);
      } else if (target.hasAttribute('data-class-check')) {
        const className = target.getAttribute('data-class-check');
        if (!className) {
          return;
        }
        if (target.checked) {
          ensureSelection(state.dictionary, className);
        } else {
          state.selected.delete(keyFor(state.dictionary, className));
        }
        state.lastPreviewFiles = [];
        renderClasses();
        renderMethods();
        renderSelected();
      } else if (target.hasAttribute('data-method-check')) {
        const selector = target.getAttribute('data-method-check');
        if (!selector) {
          return;
        }
        const selection = ensureSelection(state.dictionary, state.currentClass);
        const method = findCurrentMethod(selector);
        if (!state.meta && method.propertyCandidate) {
          const fieldName = method.pythonName || selector;
          const existing = selection.fields.indexOf(fieldName);
          if (target.checked && existing === -1) {
            selection.fields.push(fieldName);
            selection.fields.sort();
          } else if (!target.checked && existing !== -1) {
            selection.fields.splice(existing, 1);
          }
        } else {
          const list = state.meta ? selection.classMethods : selection.methods;
          const existing = list.findIndex((item) => item.selector === selector);
          if (target.checked && existing === -1) {
            list.push(toMethodSelection(method));
            list.sort((left, right) => left.selector.localeCompare(right.selector));
          } else if (!target.checked && existing !== -1) {
            removeMethodSelection(list, selector);
          }
        }
        state.lastPreviewFiles = [];
        renderClasses();
        renderMethods();
        renderSelected();
      }
    });

    document.getElementById('classFilter').addEventListener('input', (event) => {
      state.classFilter = event.target.value;
      renderClasses();
    });
    for (const tab of ['preview', 'diff', 'mapping', 'report']) {
      document.getElementById('tab' + tab[0].toUpperCase() + tab.slice(1)).addEventListener('click', () => {
        state.outputTab = tab;
        renderOutput();
      });
    }
    document.getElementById('connectBtn').addEventListener('click', () => void withBusy('Connecting...', connect));
    document.getElementById('launchBtn').addEventListener('click', () => void withBusy('Launching explorer...', async () => { await request('launchExplorer'); setStatus('Explorer launch command sent'); }));
    document.getElementById('openExplorerBtn').addEventListener('click', () => void request('openExplorer'));
    document.getElementById('openDocsBtn').addEventListener('click', () => void request('openDocs'));
    document.getElementById('checkBtn').addEventListener('click', () => void request('runCheck', payload()));
    document.getElementById('generateBtn').addEventListener('click', () => void request('generateWrappers', payload()));
    document.getElementById('demoBtn').addEventListener('click', () => void request('runDemo'));
    document.getElementById('saveBtn').addEventListener('click', () => void withBusy('Saving mapping...', async () => {
      const exported = await request('explorerPost', { path: '/codegen/export-selection', body: codegenSelectionPayload() });
      const result = await request('saveMapping', {
        ...exported.selection,
        codegenOutput: document.getElementById('codegenOutput').value.trim(),
        mappingPath: document.getElementById('mappingPath').value.trim()
      });
      setOutput('mapping', JSON.stringify(result.mapping, null, 2));
      setStatus('Saved ' + result.path);
    }));
    document.getElementById('loadBtn').addEventListener('click', () => void withBusy('Loading mapping...', async () => {
      const result = await request('loadMapping', payload());
      const mapping = result.mapping || {};
      document.getElementById('codegenModule').value = mapping.moduleName || mapping.codegenModule || document.getElementById('codegenModule').value;
      document.getElementById('codegenOutput').value = mapping.codegenOutput || document.getElementById('codegenOutput').value;
      applyMapping(mapping);
      state.lastPreviewFiles = [];
      renderClasses();
      renderMethods();
      renderSelected();
      setStatus(result.exists ? 'Loaded ' + result.path : 'No mapping file yet');
    }));
    document.getElementById('previewBtn').addEventListener('click', () => void withBusy('Generating preview...', async () => {
      const preview = await request('explorerPost', { path: '/codegen/preview', body: codegenSelectionPayload() });
      const files = preview.files || [];
      state.lastPreviewFiles = files;
      setOutput('preview', formatPreview(files));
      setStatus('Generated preview through /codegen/preview');
    }));
    document.getElementById('diffBtn').addEventListener('click', () => void withBusy('Diffing generated output...', async () => {
      if (!state.lastPreviewFiles.length) {
        const preview = await request('explorerPost', { path: '/codegen/preview', body: codegenSelectionPayload() });
        state.lastPreviewFiles = preview.files || [];
      }
      const files = await request('diffPreviewFiles', {
        codegenOutput: document.getElementById('codegenOutput').value.trim(),
        files: state.lastPreviewFiles
      });
      setOutput('diff', formatDiff(files));
      setStatus('Diff complete');
    }));
    document.getElementById('testBtn').addEventListener('click', () => void withBusy('Testing live targets...', async () => {
      const result = await request('testSelected', payload());
      setOutput('report', formatReport(result));
      setStatus(result.ok ? 'Live target test complete' : 'Live target test failed');
    }));

    async function init() {
      const config = await request('getConfig');
      state.explorerUrl = config.explorerUrl;
      document.getElementById('codegenModule').value = config.codegenModule;
      document.getElementById('codegenOutput').value = config.codegenOutput;
      document.getElementById('mappingPath').value = config.mappingPath;
      renderDictionaries();
      renderClasses();
      renderProtocols();
      renderMethods();
      renderSelected();
      setStatus('Explorer URL ' + state.explorerUrl);
    }

    void withBusy('Starting...', init);
  </script>
</body>
</html>`;
}
