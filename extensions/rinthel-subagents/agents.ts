/** Descubre agents: incluidos (./agents) < usuario (~/.pi/agent/agents) < proyecto (.pi/agents). */

import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { CONFIG_DIR_NAME, getAgentDir, parseFrontmatter } from "@earendil-works/pi-coding-agent";

export interface Agent {
	name: string;
	description: string;
	tools?: string[];
	thinking?: string;
	skills: string[];
	timeoutSec: number;
	maxTurns: number;
	prompt: string;
}

// Modelo local lento: ningun agent baja de estos minimos, ni por frontmatter.
const MIN_TIMEOUT_SEC = 1200;
const MIN_MAX_TURNS = 60;
const BUNDLED_DIR = path.join(path.dirname(fileURLToPath(import.meta.url)), "agents");

/** Acepta `a, b` o `[a, b]`. */
function toList(value: unknown): string[] {
	const raw = Array.isArray(value) ? value : typeof value === "string" ? value.split(",") : [];
	return raw.filter((v): v is string => typeof v === "string").map((v) => v.trim()).filter(Boolean);
}

function toPositive(value: unknown, fallback: number): number {
	const n = Number(value);
	return Number.isFinite(n) && n > 0 ? Math.floor(n) : fallback;
}

function loadDir(dir: string): Agent[] {
	if (!fs.existsSync(dir)) return [];
	const agents: Agent[] = [];
	for (const file of fs.readdirSync(dir)) {
		if (!file.endsWith(".md")) continue;
		try {
			const { frontmatter: fm, body } = parseFrontmatter<Record<string, unknown>>(
				fs.readFileSync(path.join(dir, file), "utf-8"),
			);
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
			});
		} catch {
			// un archivo malo no debe tumbar a los demas
		}
	}
	return agents;
}

function findProjectDir(cwd: string): string | null {
	for (let dir = cwd; ; dir = path.dirname(dir)) {
		const candidate = path.join(dir, CONFIG_DIR_NAME, "agents");
		if (fs.existsSync(candidate)) return candidate;
		if (path.dirname(dir) === dir) return null;
	}
}

export function discoverAgents(cwd: string, includeProject: boolean): Agent[] {
	const byName = new Map<string, Agent>();
	const projectDir = includeProject ? findProjectDir(cwd) : null;
	for (const dir of [BUNDLED_DIR, path.join(getAgentDir(), "agents"), projectDir]) {
		if (dir) for (const agent of loadDir(dir)) byName.set(agent.name, agent);
	}
	return [...byName.values()];
}
