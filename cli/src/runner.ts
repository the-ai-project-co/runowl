/**
 * Python backend runner.
 *
 * Discovers the Python interpreter (uv, python3, python) and spawns
 * the runowl Python package as a subprocess, streaming its output.
 */

import { spawn, type ChildProcess } from "child_process";
import { which } from "./which.js";

export interface RunnerOptions {
  command: string;
  args: string[];
  env?: Record<string, string>;
  onStdout?: (line: string) => void;
  onStderr?: (line: string) => void;
}

export interface RunnerResult {
  exitCode: number;
}

/** Find the Python executable to use. */
async function findPython(): Promise<string> {
  // Prefer uv run (handles venv automatically)
  const uv = await which("uv");
  if (uv) return uv;

  const py3 = await which("python3");
  if (py3) return py3;

  const py = await which("python");
  if (py) return py;

  throw new Error(
    "Python not found. Please install Python 3.12+ or uv.\n" +
      "  Install uv: https://docs.astral.sh/uv/getting-started/installation/\n" +
      "  Install Python: https://python.org/downloads/"
  );
}

/** Build the command + args to invoke the Python CLI. */
async function buildCommand(
  command: string,
  args: string[]
): Promise<[string, string[]]> {
  const pythonOrUv = await findPython();

  if (pythonOrUv.endsWith("uv")) {
    // uv run python -m runowl.cli <command> <args...>
    return [pythonOrUv, ["run", "python", "-m", "runowl.cli", command, ...args]];
  }

  // python3 -m runowl.cli <command> <args...>
  return [pythonOrUv, ["-m", "runowl.cli", command, ...args]];
}

/** Run the Python backend and stream output line-by-line. */
export async function runPython(options: RunnerOptions): Promise<RunnerResult> {
  const [exe, baseArgs] = await buildCommand(options.command, options.args);

  const env: NodeJS.ProcessEnv = {
    ...process.env,
    ...options.env,
    // Disable Python output buffering so we get streaming output
    PYTHONUNBUFFERED: "1",
  };

  const child: ChildProcess = spawn(exe, baseArgs, {
    env,
    stdio: ["inherit", "pipe", "pipe"],
  });

  // Stream stdout line-by-line
  let stdoutBuf = "";
  child.stdout?.on("data", (chunk: Buffer) => {
    stdoutBuf += chunk.toString();
    const lines = stdoutBuf.split("\n");
    stdoutBuf = lines.pop() ?? "";
    for (const line of lines) {
      if (options.onStdout) {
        options.onStdout(line);
      } else {
        process.stdout.write(line + "\n");
      }
    }
  });

  // Stream stderr line-by-line
  let stderrBuf = "";
  child.stderr?.on("data", (chunk: Buffer) => {
    stderrBuf += chunk.toString();
    const lines = stderrBuf.split("\n");
    stderrBuf = lines.pop() ?? "";
    for (const line of lines) {
      if (options.onStderr) {
        options.onStderr(line);
      } else {
        process.stderr.write(line + "\n");
      }
    }
  });

  return new Promise((resolve, reject) => {
    child.on("error", (err) => {
      reject(new Error(`Failed to start Python backend: ${err.message}`));
    });

    child.on("close", (code) => {
      // Flush remaining buffers
      if (stdoutBuf && options.onStdout) options.onStdout(stdoutBuf);
      if (stderrBuf && options.onStderr) options.onStderr(stderrBuf);

      resolve({ exitCode: code ?? 0 });
    });
  });
}
