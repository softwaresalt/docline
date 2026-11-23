const readline = require("node:readline");
const { spawn } = require("node:child_process");
const path = require("node:path");

const [command, ...args] = process.argv.slice(2);

if (!command) {
  console.error("Usage: bun stdio-shim.cjs <command> [args...]");
  process.exit(2);
}

const extension = path.extname(command).toLowerCase();
const launchCommand = [".js", ".cjs", ".mjs"].includes(extension)
  ? process.execPath
  : command;
const launchArgs = launchCommand === command ? args : [command, ...args];
const child = spawn(launchCommand, launchArgs, {
  env: process.env,
  stdio: ["pipe", "pipe", "pipe"],
});

let initializeId;
let initializeResponseSeen = false;
let initializedSent = false;
const queuedClientMessages = [];

function parseMessage(line) {
  try {
    return JSON.parse(line);
  } catch {
    return undefined;
  }
}

function writeToChild(line) {
  child.stdin.write(`${line}\n`);
}

function sendInitialized() {
  if (initializedSent) {
    return;
  }

  writeToChild(
    JSON.stringify({
      jsonrpc: "2.0",
      method: "notifications/initialized",
      params: {},
    }),
  );
  initializedSent = true;
}

function flushQueuedClientMessages() {
  if (!initializeResponseSeen || queuedClientMessages.length === 0) {
    return;
  }

  sendInitialized();
  for (const line of queuedClientMessages.splice(0)) {
    writeToChild(line);
  }
}

const clientLines = readline.createInterface({
  input: process.stdin,
  crlfDelay: Infinity,
});

clientLines.on("line", (line) => {
  const message = parseMessage(line);

  if (message?.method === "server/discover") {
    process.stdout.write(
      `${JSON.stringify({
        jsonrpc: "2.0",
        id: message.id,
        result: {},
      })}\n`,
    );
    return;
  }

  if (message?.method === "initialize") {
    initializeId = message.id;
    writeToChild(line);
    return;
  }

  if (message?.method === "notifications/initialized") {
    if (!initializedSent) {
      writeToChild(line);
      initializedSent = true;
    }
    return;
  }

  if (initializeId !== undefined && !initializeResponseSeen) {
    queuedClientMessages.push(line);
    return;
  }

  if (initializeResponseSeen) {
    sendInitialized();
  }

  writeToChild(line);
});

clientLines.on("close", () => {
  child.stdin.end();
});

const serverLines = readline.createInterface({
  input: child.stdout,
  crlfDelay: Infinity,
});

serverLines.on("line", (line) => {
  const message = parseMessage(line);

  if (message?.id === initializeId && message.result) {
    initializeResponseSeen = true;
  }

  process.stdout.write(`${line}\n`);
  flushQueuedClientMessages();
});

child.stderr.pipe(process.stderr);

child.on("error", (error) => {
  console.error(`Failed to launch MCP server: ${error.message}`);
  process.exitCode = 2;
});

child.on("close", (code, signal) => {
  if (signal) {
    console.error(`MCP server terminated by signal ${signal}`);
    process.exitCode = 2;
    return;
  }

  process.exitCode = code ?? 0;
});
