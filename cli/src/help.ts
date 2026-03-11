/**
 * Help and version output.
 */

import { createRequire } from "module";
import { fileURLToPath } from "url";
import { dirname, join } from "path";
import { readFileSync } from "fs";

function getVersion(): string {
  try {
    const __filename = fileURLToPath(import.meta.url);
    const __dirname = dirname(__filename);
    const pkgPath = join(__dirname, "..", "package.json");
    const pkg = JSON.parse(readFileSync(pkgPath, "utf-8")) as { version: string };
    return pkg.version;
  } catch {
    return "0.1.0";
  }
}

export function printVersion(): void {
  console.log(`runowl/${getVersion()}`);
}

export function printHelp(): void {
  console.log(`
runowl — AI-powered PR code review

Usage:
  runowl review --url <github-pr-url> [options]
  runowl ask    --url <github-pr-url> [--question <q>]

Commands:
  review    Run a full AI code review on a GitHub PR
  ask       Ask a question about a PR in interactive mode

Review options:
  -u, --url <url>         GitHub PR URL (required)
  -q, --question <q>      Ask a specific question instead of full review
      --expert            Enable deep security + SOLID analysis (paid)
  -o, --output <format>   Output format: text (default), markdown, json
      --quiet             Suppress progress output, show results only
      --submit            Post the review as a GitHub PR comment
  -m, --model <model>     Gemini model to use (default: gemini-2.0-flash)

Ask options:
  -u, --url <url>         GitHub PR URL (required)
  -q, --question <q>      Question to ask (starts interactive session if omitted)

Global options:
  -V, --version           Show version
  -h, --help              Show this help

Examples:
  npx runowl review --url https://github.com/owner/repo/pull/42
  npx runowl review --url https://github.com/owner/repo/pull/42 --expert --output json
  npx runowl ask    --url https://github.com/owner/repo/pull/42

Environment variables:
  GEMINI_API_KEY     Required — Gemini API key
  GITHUB_TOKEN       Optional — for private repos
  RUNOWL_TIER        Optional — free (default) or team

Learn more: https://runowl.ai
`.trim());
}
