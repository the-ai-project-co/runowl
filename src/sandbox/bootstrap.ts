/**
 * RunOwl Deno Sandbox Bootstrap
 *
 * This script runs inside `deno run` with strict permission flags.
 * It receives agent code via stdin, executes it in a controlled context,
 * and enforces the tool whitelist (SEARCH_CODE, FETCH_FILE, LIST_DIR only).
 *
 * Blocked: all file I/O, network calls, subprocess spawning, eval of
 * arbitrary code outside the provided agent script.
 */

const ALLOWED_TOOLS = new Set(["SEARCH_CODE", "FETCH_FILE", "LIST_DIR"]);

// Context injected by the Python runner
const contextRaw = Deno.env.get("RUNOWL_CONTEXT") ?? "{}";
const agentCode = Deno.env.get("RUNOWL_AGENT_CODE") ?? "";

let context: Record<string, unknown>;
try {
  context = JSON.parse(contextRaw);
} catch {
  console.error("Failed to parse RUNOWL_CONTEXT");
  Deno.exit(1);
}

/**
 * Tool dispatch — only whitelisted tools may be called.
 * Results are written to stdout as TOOL_CALL:<json> lines so the
 * Python runner can parse them back.
 */
function callTool(name: string, args: Record<string, unknown>): unknown {
  if (!ALLOWED_TOOLS.has(name)) {
    throw new Error(
      `Tool '${name}' is not allowed in the sandbox. ` +
        `Allowed: ${[...ALLOWED_TOOLS].join(", ")}`
    );
  }

  const result = { tool: name, args, result: null as unknown, error: null as string | null };

  try {
    // Tools are resolved against the injected context.
    // Real implementations delegate back to the Python host via stdout.
    // The Python runner reads TOOL_CALL lines and fulfils them.
    switch (name) {
      case "SEARCH_CODE":
        result.result = { status: "dispatched", query: args["query"] };
        break;
      case "FETCH_FILE":
        result.result = { status: "dispatched", path: args["path"] };
        break;
      case "LIST_DIR":
        result.result = { status: "dispatched", path: args["path"] };
        break;
    }
  } catch (err) {
    result.error = String(err);
  }

  // Emit structured tool call for the Python runner to capture
  console.log(`TOOL_CALL:${JSON.stringify(result)}`);
  return result.result;
}

// Expose safe globals to the agent script scope
const sandboxGlobals = {
  context,
  callTool,
  SEARCH_CODE: (query: string) => callTool("SEARCH_CODE", { query }),
  FETCH_FILE: (path: string) => callTool("FETCH_FILE", { path }),
  LIST_DIR: (path: string) => callTool("LIST_DIR", { path }),
  console,
};

// Execute the agent code in a restricted scope
if (agentCode) {
  try {
    const fn = new Function(
      ...Object.keys(sandboxGlobals),
      `"use strict";\n${agentCode}`
    );
    fn(...Object.values(sandboxGlobals));
  } catch (err) {
    console.error(`Agent execution error: ${err}`);
    Deno.exit(1);
  }
}
