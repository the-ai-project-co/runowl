/**
 * `runowl review` command handler.
 *
 * Builds the Python CLI args and delegates to the Python backend,
 * which handles all formatting via Rich.
 */

import { type ParsedArgs } from "./args.js";
import { runPython } from "./runner.js";

export async function runReview(args: ParsedArgs): Promise<void> {
  if (!args.url) {
    throw new Error("--url is required for the review command.\n  Example: runowl review --url https://github.com/owner/repo/pull/42");
  }

  const pyArgs: string[] = ["--url", args.url];

  if (args.question) {
    pyArgs.push("--question", args.question);
  }
  if (args.expert) {
    pyArgs.push("--expert");
  }
  if (args.output !== "text") {
    pyArgs.push("--output", args.output);
  }
  if (args.quiet) {
    pyArgs.push("--quiet");
  }
  if (args.submit) {
    pyArgs.push("--submit");
  }
  if (args.model) {
    pyArgs.push("--model", args.model);
  }

  const result = await runPython({
    command: "review",
    args: pyArgs,
  });

  process.exit(result.exitCode);
}
