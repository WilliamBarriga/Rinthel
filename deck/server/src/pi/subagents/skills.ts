import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

/**
 * The skills Deck ships in its image (`deck/skills/`), next to the server: `server/{src,dist}/pi/subagents`
 * is three levels below `deck/` both from source and built. `undefined` when the directory is not there.
 */
export function shippedSkillsDir(): string | undefined {
  const dir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../../skills");
  return existsSync(dir) ? dir : undefined;
}

/** The skills a child asked for, by name: in the Session's working directory, in Deck's agentDir, then the shipped ones. */
export interface ChildSkills {
  /** Directories the child loads on demand. */
  dirs: string[];
  found: string[];
  missing: string[];
  /** Whole `SKILL.md` files, when they are pasted into the prompt instead. */
  inlined: string;
}

function find(name: string, cwd: string, agentDir: string): string | null {
  if (!/^[\w.-]+$/.test(name)) return null;
  const shipped = shippedSkillsDir();
  const roots = [path.join(cwd, ".pi", "skills"), path.join(cwd, ".agents", "skills"), path.join(agentDir, "skills"), ...(shipped ? [shipped] : [])];
  for (const root of roots) {
    const dir = path.join(root, name);
    if (existsSync(path.join(dir, "SKILL.md"))) return dir;
  }
  return null;
}

/** `inline` false: the child sees the skill and reads it when it needs it. True: its `SKILL.md` is pasted whole. */
export function resolveSkills(names: string[], cwd: string, agentDir: string, inline: boolean): ChildSkills {
  const out: ChildSkills = { dirs: [], found: [], missing: [], inlined: "" };
  const parts: string[] = [];
  for (const name of new Set(names)) {
    const dir = find(name, cwd, agentDir);
    if (!dir) {
      out.missing.push(name);
      continue;
    }
    out.found.push(name);
    if (inline) parts.push(`## Skill: ${name} (base: ${dir})\n\n${readFileSync(path.join(dir, "SKILL.md"), "utf8")}`);
    else out.dirs.push(dir);
  }
  out.inlined = parts.join("\n\n");
  return out;
}
