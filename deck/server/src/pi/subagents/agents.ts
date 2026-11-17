import { existsSync, readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

/**
 * The agent types a `subagent` call can name: the image's `agents/*.md` (next to this file), plus the
 * `agents/*.md` of Deck's agentDir on the volume. A volume file with an image agent's name replaces it,
 * and the replacement is logged. A project's `.pi/agents` is never read.
 *
 * Frontmatter: `name`, `description` (both required), `tools`, `thinking`, `skills`, `timeout`,
 * `maxTurns`; the body is the agent's prompt.
 */
export interface AgentType {
  name: string;
  description: string;
  /** pi's allowlist for the child; absent, pi's defaults. */
  tools?: string[];
  thinking?: string;
  skills: string[];
  timeoutSec: number;
  maxTurns: number;
  prompt: string;
  /** The file it was read from. */
  file: string;
}

/** A local model is slow: no agent goes below these, whatever its frontmatter says. */
const MIN_TIMEOUT_SEC = 1200;
const MIN_MAX_TURNS = 60;

/** The image's agents. The server build copies them next to the compiled module. */
export const IMAGE_AGENTS_DIR = path.join(path.dirname(fileURLToPath(import.meta.url)), "agents");

type ParseFrontmatter = (text: string) => { frontmatter: Record<string, unknown>; body: string };

/** Takes `a, b` or `[a, b]`. */
function toList(value: unknown): string[] {
  const raw = Array.isArray(value) ? value : typeof value === "string" ? value.split(",") : [];
  return raw.filter((v): v is string => typeof v === "string").map((v) => v.trim()).filter(Boolean);
}

function toPositive(value: unknown, fallback: number): number {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : fallback;
}

function loadDir(dir: string, parse: ParseFrontmatter): AgentType[] {
  if (!existsSync(dir)) return [];
  const agents: AgentType[] = [];
  for (const name of readdirSync(dir).sort()) {
    if (!name.endsWith(".md")) continue;
    const file = path.join(dir, name);
    try {
      const { frontmatter: fm, body } = parse(readFileSync(file, "utf8"));
      if (typeof fm.name !== "string" || typeof fm.description !== "string") continue;
      const tools = toList(fm.tools);
      agents.push({
        name: fm.name,
        description: fm.description,
        tools: tools.length > 0 ? tools : undefined,
        thinking: typeof fm.thinking === "string" ? fm.thinking : undefined,
        skills: toList(fm.skills),
        timeoutSec: Math.max(MIN_TIMEOUT_SEC, toPositive(fm.timeout, MIN_TIMEOUT_SEC)),
        maxTurns: Math.max(MIN_MAX_TURNS, toPositive(fm.maxTurns, MIN_MAX_TURNS)),
        prompt: body.trim(),
        file,
      });
    } catch {
      // One bad file does not take the others down.
    }
  }
  return agents;
}

/** The image's agents and the volume's, by name; `log` hears of each image agent the volume replaces. */
export async function discoverAgents(agentDir: string, log: (line: string) => void = () => {}): Promise<AgentType[]> {
  // Imported lazily: importing this module must not load pi.
  const { parseFrontmatter } = await import("@earendil-works/pi-coding-agent");
  const parse = parseFrontmatter as ParseFrontmatter;
  const byName = new Map(loadDir(IMAGE_AGENTS_DIR, parse).map((a) => [a.name, a]));
  for (const agent of loadDir(path.join(agentDir, "agents"), parse)) {
    const image = byName.get(agent.name);
    if (image) log(`[subagents] agent "${agent.name}": ${agent.file} replaces the image's ${image.file}`);
    byName.set(agent.name, agent);
  }
  return [...byName.values()];
}
