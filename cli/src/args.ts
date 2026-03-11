/**
 * Minimal argument parser for runowl CLI.
 *
 * Supports:
 *   runowl review --url <pr> [--question <q>] [--expert] [--output text|markdown|json]
 *                            [--quiet] [--submit] [--model <model>]
 *   runowl ask    --url <pr> [--question <q>]
 *   runowl --version / -V
 *   runowl --help / -h
 */

export interface ParsedArgs {
  command?: "review" | "ask";
  url?: string;
  question?: string;
  expert: boolean;
  output: "text" | "markdown" | "json";
  quiet: boolean;
  submit: boolean;
  model?: string;
  version: boolean;
  help: boolean;
}

export function parseArgs(argv: string[]): ParsedArgs {
  const result: ParsedArgs = {
    expert: false,
    output: "text",
    quiet: false,
    submit: false,
    version: false,
    help: false,
  };

  let i = 0;

  const peek = (): string | undefined => argv[i];
  const next = (): string => {
    const val = argv[i++];
    if (val === undefined) throw new Error("Expected value after flag");
    return val;
  };

  // First positional arg is the command
  if (argv[0] && !argv[0].startsWith("-")) {
    const cmd = argv[0] as string;
    if (cmd === "review" || cmd === "ask") {
      result.command = cmd;
      i = 1;
    }
  }

  while (i < argv.length) {
    const arg = peek()!;
    i++;

    switch (arg) {
      case "--url":
      case "-u":
        result.url = next();
        break;
      case "--question":
      case "-q":
        result.question = next();
        break;
      case "--expert":
        result.expert = true;
        break;
      case "--output":
      case "-o": {
        const val = next();
        if (val !== "text" && val !== "markdown" && val !== "json") {
          throw new Error(`Invalid --output value '${val}'. Must be text, markdown, or json.`);
        }
        result.output = val;
        break;
      }
      case "--quiet":
        result.quiet = true;
        break;
      case "--submit":
        result.submit = true;
        break;
      case "--model":
      case "-m":
        result.model = next();
        break;
      case "--version":
      case "-V":
        result.version = true;
        break;
      case "--help":
      case "-h":
        result.help = true;
        break;
      default:
        throw new Error(`Unknown flag: ${arg}`);
    }
  }

  return result;
}
