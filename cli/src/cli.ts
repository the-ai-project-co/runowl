#!/usr/bin/env node
/**
 * RunOwl CLI — entry point for `npx runowl`
 *
 * Commands:
 *   runowl review  --url <pr-url>   [options]
 *   runowl ask     --url <pr-url>   [--question <q>]
 */

import { parseArgs } from "./args.js";
import { runReview } from "./review.js";
import { runAsk } from "./ask.js";
import { printHelp, printVersion } from "./help.js";

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));

  if (args.version) {
    printVersion();
    process.exit(0);
  }

  if (args.help || !args.command) {
    printHelp();
    process.exit(0);
  }

  switch (args.command) {
    case "review":
      await runReview(args);
      break;
    case "ask":
      await runAsk(args);
      break;
    default:
      console.error(`Unknown command: ${args.command}`);
      printHelp();
      process.exit(1);
  }
}

main().catch((err: unknown) => {
  const message = err instanceof Error ? err.message : String(err);
  console.error(`\nError: ${message}`);
  process.exit(1);
});
