import { execFile } from "node:child_process";
import { promisify } from "node:util";
import type { PiPackages } from "./pi-packages.js";

const run = promisify(execFile);

/** How long one pi package command may take: an install downloads from the network. */
const PI_CLI_TIMEOUT_MS = 120_000;

/**
 * `PiPackages` over pi's CLI (`pi list|install|remove|update`), which installs under `$HOME/.pi/agent`:
 * on Deck's volume, so packages survive an image rebuild. The spec reaches the CLI as one argument,
 * never through a shell. `command` is the CLI (`pi` on the image's PATH).
 */
export function piPackagesCli(command = "pi"): PiPackages {
  const pi = async (args: string[]): Promise<string> => {
    try {
      const { stdout, stderr } = await run(command, args, { timeout: PI_CLI_TIMEOUT_MS, maxBuffer: 4 * 1024 * 1024 });
      return `${stdout}${stderr}`;
    } catch (e) {
      const err = e as { stdout?: string; stderr?: string; message: string };
      throw new Error((err.stderr || err.stdout || err.message).trim());
    }
  };
  return {
    list: () => pi(["list"]),
    install: (spec) => pi(["install", spec]),
    remove: (spec) => pi(["remove", spec]),
    update: () => pi(["update", "--all"]),
  };
}
