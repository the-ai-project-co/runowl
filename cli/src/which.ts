/**
 * Cross-platform `which` utility — resolves a command to its full path.
 */

import { exec } from "child_process";
import { promisify } from "util";

const execAsync = promisify(exec);

export async function which(command: string): Promise<string | null> {
  const whichCmd = process.platform === "win32" ? "where" : "which";
  try {
    const { stdout } = await execAsync(`${whichCmd} ${command}`);
    const path = stdout.trim().split("\n")[0]?.trim();
    return path ?? null;
  } catch {
    return null;
  }
}
