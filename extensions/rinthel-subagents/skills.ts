/** Resuelve skills por nombre buscando en las carpetas de skills conocidas. */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { CONFIG_DIR_NAME, getAgentDir } from "@earendil-works/pi-coding-agent";

export interface Skills {
	dirs: string[]; // carpetas para cargar bajo demanda
	names: string[]; // skills encontradas
	missing: string[]; // skills no encontradas
	inlined: string; // SKILL.md completos (solo si inline)
}

function find(name: string, cwd: string): string | null {
	if (!/^[\w.-]+$/.test(name)) return null;
	const roots = [
		path.join(cwd, CONFIG_DIR_NAME, "skills"),
		path.join(cwd, ".agents", "skills"),
		path.join(getAgentDir(), "skills"),
		path.join(os.homedir(), ".agents", "skills"),
	];
	for (const root of roots) {
		const dir = path.join(root, name);
		if (fs.existsSync(path.join(dir, "SKILL.md"))) return dir;
	}
	return null;
}

/** inline=false: el subagente ve la skill y la lee si la necesita. inline=true: se pega el SKILL.md completo. */
export function resolveSkills(names: string[], cwd: string, inline: boolean): Skills {
	const out: Skills = { dirs: [], names: [], missing: [], inlined: "" };
	const parts: string[] = [];
	for (const name of new Set(names)) {
		const dir = find(name, cwd);
		if (!dir) {
			out.missing.push(name);
			continue;
		}
		out.names.push(name);
		if (inline) parts.push(`## Skill: ${name} (base: ${dir})\n\n${fs.readFileSync(path.join(dir, "SKILL.md"), "utf-8")}`);
		else out.dirs.push(dir);
	}
	out.inlined = parts.join("\n\n");
	return out;
}
