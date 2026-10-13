/**
 * Tool `subagent`, siempre en serie.
 *
 *   single: { agent, task }
 *   chain:  { chain: [{ agent, task }] }   cada paso recibe {previous}
 *   tasks:  { tasks: [{ agent, task }] }   independientes, una tras otra (variants: true = alternativas)
 *
 * Opcionales: skills (global o por item), persona (rol para esta tarea), inlineSkills.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { discoverAgents } from "./agents.ts";
import { type Result, runAgent } from "./runner.ts";

const MAX_TASKS = 8;
const OUTPUT_CAP = 50 * 1024;

const Item = Type.Object({
	agent: Type.String({ description: "Nombre del agent" }),
	task: Type.String({ description: "Tarea. En chain, {previous} = salida del paso anterior" }),
	skills: Type.Optional(Type.Array(Type.String(), { description: "Skills extra solo para este item" })),
	persona: Type.Optional(Type.String({ description: "Rol para este item (util con agent custom)" })),
});

const Params = Type.Object({
	agent: Type.Optional(Type.String({ description: "Modo single: nombre del agent" })),
	task: Type.Optional(Type.String({ description: "Modo single: tarea" })),
	chain: Type.Optional(Type.Array(Item, { description: "Pasos dependientes, en orden" })),
	tasks: Type.Optional(Type.Array(Item, { description: "Tareas independientes, en secuencia" })),
	variants: Type.Optional(Type.Boolean({ description: "Con tasks: son alternativas para comparar" })),
	skills: Type.Optional(Type.Array(Type.String(), { description: "Skills para todos los items" })),
	persona: Type.Optional(Type.String({ description: "Persona para todos los items" })),
	inlineSkills: Type.Optional(Type.Boolean({ description: "Pegar el SKILL.md completo en vez de cargarlo bajo demanda" })),
});

const cap = (text: string) => (text.length > OUTPUT_CAP ? `${text.slice(0, OUTPUT_CAP)}\n\n[truncated]` : text);

export interface Details {
	mode: "single" | "chain" | "tasks";
	results: Result[];
}

export function registerSubagent(pi: ExtensionAPI, render: Record<string, unknown> = {}) {
	// Solo agents incluidos y de usuario: los de proyecto dependen del cwd/confianza de cada sesion y se validan en execute.
	const catalog = discoverAgents(process.cwd(), false)
		.map((a) => `${a.name}: ${a.description}`)
		.join(" | ");

	pi.registerTool({
		name: "subagent",
		label: "Subagent",
		description:
			"Delega trabajo a subagentes con contexto aislado. Corren de a uno (modelo local). " +
			"Modos: single (agent+task), chain (pasos con {previous}), tasks (independientes; variants:true para alternativas). " +
			`Agents: ${catalog}.`,
		parameters: Params,
		...render,

		async execute(_id, params, signal, onUpdate, ctx) {
			const agents = discoverAgents(ctx.cwd, ctx.isProjectTrusted());
			const mode = params.chain?.length ? "chain" : params.tasks?.length ? "tasks" : "single";
			const items =
				mode === "chain" ? params.chain! : mode === "tasks" ? params.tasks! : params.agent && params.task ? [{ agent: params.agent, task: params.task }] : [];
			const fail = (text: string) => ({ content: [{ type: "text" as const, text }], details: { mode, results: [] } as Details, isError: true });

			if (items.length === 0) return fail(`Falta agent+task, chain o tasks. Agents: ${catalog}`);
			if (items.length > MAX_TASKS) return fail(`Demasiados items (${items.length}); maximo ${MAX_TASKS}.`);
			const unknown = items.find((i) => !agents.some((a) => a.name === i.agent));
			if (unknown) return fail(`Agent desconocido "${unknown.agent}". Disponibles: ${agents.map((a) => a.name).join(", ")}`);

			const results: Result[] = [];
			let previous = "";
			for (const [index, item] of (items as Array<{ agent: string; task: string; skills?: string[]; persona?: string }>).entries()) {
				const agent = agents.find((a) => a.name === item.agent)!;
				const task = mode === "chain" && index > 0 ? item.task.replaceAll("{previous}", previous) : item.task;
				const result = await runAgent(agent, task, {
					cwd: ctx.cwd,
					model: ctx.model,
					thinking: ctx.thinkingLevel,
					skills: [...(params.skills ?? []), ...(item.skills ?? [])],
					inlineSkills: params.inlineSkills ?? false,
					persona: item.persona ?? params.persona,
					signal,
					onProgress: (partial) =>
						onUpdate?.({ content: [{ type: "text", text: partial.output || "(running...)" }], details: { mode, results: [...results, partial] } as Details }),
				});
				results.push(result);
				previous = cap(result.output);
				if (!result.ok && mode === "chain") {
					return { ...fail(`Chain detenida en el paso ${results.length} (${item.agent}): ${result.output}`), details: { mode, results } as Details };
				}
			}

			const text =
				mode === "single"
					? cap(results[0].output)
					: mode === "chain"
						? cap(results[results.length - 1].output)
						: results
								.map((r, i) => `### ${params.variants ? "Variante" : "Tarea"} ${i + 1} [${r.agent}] ${r.ok ? "ok" : "fallo"}\n\n${cap(r.output)}`)
								.join("\n\n---\n\n");
			return { content: [{ type: "text", text: text || "(sin salida)" }], details: { mode, results } as Details, isError: results.some((r) => !r.ok) && mode === "single" };
		},
	});
}
