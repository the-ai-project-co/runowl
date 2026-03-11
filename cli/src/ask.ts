/**
 * `runowl ask` command handler.
 *
 * Starts an interactive Q&A session or asks a single question.
 * Delegates fully to the Python backend for formatting and session management.
 */

import { type ParsedArgs } from "./args.js";
import { runPython } from "./runner.js";

export async function runAsk(args: ParsedArgs): Promise<void> {
  if (!args.url) {
    throw new Error("--url is required for the ask command.\n  Example: runowl ask --url https://github.com/owner/repo/pull/42");
  }

  const pyArgs: string[] = ["--url", args.url];

  if (args.question) {
    pyArgs.push("--question", args.question);
  }
  if (args.quiet) {
    pyArgs.push("--quiet");
  }
  if (args.model) {
    pyArgs.push("--model", args.model);
  }

  const result = await runPython({
    command: "ask",
    args: pyArgs,
  });

  process.exit(result.exitCode);
}
