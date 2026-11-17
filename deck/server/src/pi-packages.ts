/**
 * Port: the pi packages (extensions, skills, prompts, themes) installed in Deck's agentDir, on the
 * volume. What Deck needs ships in its image; extras are packages an admin installs here, and every
 * admin Session started afterwards loads them. Each call answers pi's own output, or throws its error.
 */
export interface PiPackages {
  list(): Promise<string>;
  install(spec: string): Promise<string>;
  remove(spec: string): Promise<string>;
  /** Updates every installed package. */
  update(): Promise<string>;
}

/**
 * The package shapes pi documents (`npm:pkg@1.0.0`, `git:github.com/user/repo`, `https://…`, a path).
 * A spec is passed as one argument, never a shell string; anything else is refused before pi runs.
 */
export const PACKAGE_SPEC = /^(npm:|git:|https:\/\/|\.{0,2}\/)[\w@./:+-]+$/;

/** The double: what an install would leave, in memory. `calls` lists each call that reached it. */
export class InMemoryPiPackages implements PiPackages {
  readonly calls: string[] = [];
  readonly installed: string[] = [];
  /** While set, every call throws this, as pi failing would. */
  failWith: string | null = null;

  private record(call: string): void {
    this.calls.push(call);
    if (this.failWith) throw new Error(this.failWith);
  }

  async list(): Promise<string> {
    this.record("list");
    return this.installed.length ? this.installed.join("\n") : "No packages installed.";
  }

  async install(spec: string): Promise<string> {
    this.record(`install ${spec}`);
    if (!this.installed.includes(spec)) this.installed.push(spec);
    return `Installed ${spec}`;
  }

  async remove(spec: string): Promise<string> {
    this.record(`remove ${spec}`);
    const at = this.installed.indexOf(spec);
    if (at < 0) throw new Error(`${spec} is not installed`);
    this.installed.splice(at, 1);
    return `Removed ${spec}`;
  }

  async update(): Promise<string> {
    this.record("update");
    return "Everything is up to date.";
  }
}
