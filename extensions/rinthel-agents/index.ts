/**
 * Rinthel Agents — Subagentes Secuenciales Determinísticos
 *
 * Extensión que permite al main agent delegar tareas a subagentes especializados.
 * Cada subagente corre como una AgentSession propia, separada, creada y esperada
 * (await) dentro del execute() del tool — no como un turno nuevo inyectado en la
 * sesión principal. Eso es lo que hace que el main agent efectivamente espere el
 * resultado y lo reciba de vuelta como parte de su propio turno.
 *
 * 4 funciones expuestas:
 * - subagent(agent, task) — una tarea simple
 * - subagentChain(agent, tasks) — cola dependiente (output de N → input de N+1)
 * - subagentSeries(agent, tasks) — tareas independientes en secuencia
 * - subagentVariants(agent, tasks, continue) — exploración con variantes
 */

import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import {
	createAgentSession,
	DefaultResourceLoader,
	getAgentDir,
	SessionManager,
} from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { readFileSync, existsSync } from "node:fs";
import { join } from "node:path";

// ─── Constants ───────────────────────────────────────────────────────────────

const AGENTS_DIR = join(process.env.HOME || "/data/home", ".pi", "agent", "agents");
const MAX_CONTEXT_CHARS = 8000; // Stop chain context accumulation past this size

// Built-ins only — deliberately excludes subagent/subagentChain/subagentSeries/
// subagentVariants, so a subagent can't spawn its own nested subagents.
const SUBAGENT_TOOLS = ["read", "bash", "edit", "write", "grep", "find", "ls"];

// ─── Types ───────────────────────────────────────────────────────────────────

interface AgentFile {
	name: string;
	displayName: string;
	systemPrompt: string;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** Parse frontmatter from an agent markdown file */
function parseAgentFile(content: string): AgentFile {
	const fmMatch = content.match(/^---\n([\s\S]*?)\n---\n([\s\S]*)$/);
	if (!fmMatch) {
		throw new Error(`Invalid agent file format (missing frontmatter)`);
	}

	const fmLines = fmMatch[1].split("\n");
	const meta: Record<string, string> = {};
	for (const line of fmLines) {
		const [key, ...rest] = line.split(": ");
		if (key && rest.length) {
			meta[key.trim()] = rest.join(": ").trim();
		}
	}

	return {
		name: meta.name || "unknown",
		displayName: meta.displayName || meta.name || "Unknown",
		systemPrompt: fmMatch[2].trim(),
	};
}

/** Load an agent file by name */
function loadAgent(name: string): AgentFile {
	const filePath = join(AGENTS_DIR, `${name}.md`);
	if (!existsSync(filePath)) {
		throw new Error(`Agente "${name}" no encontrado en ${AGENTS_DIR}`);
	}
	const content = readFileSync(filePath, "utf-8");
	return parseAgentFile(content);
}

/** Concatenate the assistant's text output from a finished session (skips thinking/tool-call blocks) */
function extractAssistantText(messages: Array<{ role: string; content?: Array<{ type: string; text?: string }> }>): string {
	const parts: string[] = [];
	for (const msg of messages) {
		if (msg.role !== "assistant" || !msg.content) continue;
		for (const block of msg.content) {
			if (block.type === "text" && block.text) {
				parts.push(block.text);
			}
		}
	}
	return parts.join("\n\n").trim();
}

/**
 * Build context for next task in a chain.
 * Returns null if accumulated context exceeds MAX_CONTEXT_CHARS.
 */
function buildChainContext(context: string, taskIndex: number, result: string): string | null {
	const sep = "\n\n" + "─".repeat(60) + "\n";
	const newEntry = `\n## Tarea ${taskIndex + 1} completada:\n${result}`;
	const accumulated = context + sep + newEntry;

	if (accumulated.length > MAX_CONTEXT_CHARS) {
		return null; // Signal: context too large
	}

	return accumulated;
}

// Serializes subagent runs so only one is ever in flight at a time, even if the
// LLM issues sibling subagent tool calls concurrently (pi's default parallel
// tool-call mode runs sibling tool calls from the same assistant message at
// the same time).
let queueTail: Promise<unknown> = Promise.resolve();
function serialize<T>(fn: () => Promise<T>): Promise<T> {
	const run = queueTail.then(fn, fn);
	queueTail = run.then(
		() => undefined,
		() => undefined,
	);
	return run;
}

// Chain context accumulated across subagentChain calls, per agent. In-memory
// only: lost on extension reload or process restart, which just means the
// next subagentChain call starts a fresh chain instead of resuming a stale one.
let chainState: { agent: string; context: string; completedCount: number } | null = null;

/**
 * Run one subagent task to completion in its own, separate AgentSession and
 * return its final assistant text. Awaited synchronously by the caller, so
 * the calling tool call — and therefore the main agent's turn — actually
 * blocks on the result instead of firing a task off into the void.
 */
async function runSubagentTurn(
	ctx: ExtensionContext,
	agentName: string,
	task: string,
	extraContext?: string,
): Promise<string> {
	const agent = loadAgent(agentName);
	const systemPrompt = extraContext
		? `${agent.systemPrompt}\n\n## Contexto acumulado de tareas anteriores:\n${extraContext}`
		: agent.systemPrompt;

	const loader = new DefaultResourceLoader({
		cwd: ctx.cwd,
		agentDir: getAgentDir(),
		systemPromptOverride: () => systemPrompt,
	});
	await loader.reload();

	const { session: sub } = await createAgentSession({
		cwd: ctx.cwd,
		model: ctx.model,
		tools: SUBAGENT_TOOLS,
		resourceLoader: loader,
		sessionManager: SessionManager.inMemory(ctx.cwd),
	});

	try {
		await sub.prompt(task);
		const text = extractAssistantText(sub.messages as Array<{ role: string; content?: Array<{ type: string; text?: string }> }>);
		return text || "(el subagente no devolvió texto)";
	} finally {
		sub.dispose();
	}
}

// ─── Extension ───────────────────────────────────────────────────────────────

export default function (pi: ExtensionAPI) {
	// 1. subagent(agent, task) — single task, blocks until the subagent finishes
	pi.registerTool({
		name: "subagent",
		label: "Subagent",
		description:
			"Delega una tarea a un subagente especializado y espera su resultado. Ejecuta un solo agente con una sola tarea.",
		parameters: Type.Object({
			agent: Type.String({ description: "Nombre del agente: scout, planner, writer, reviewer, builder, custom" }),
			task: Type.String({ description: "La tarea a ejecutar" }),
		}),
		execute: async (_toolCallId, params, _signal, _onUpdate, ctx) => {
			const agentName = params.agent as string;
			const task = params.task as string;
			const agent = loadAgent(agentName); // fail fast on bad agent name, before taking the lock

			const result = await serialize(() => runSubagentTurn(ctx, agentName, task));

			return {
				content: [
					{
						type: "text",
						text: `✅ "${agent.displayName}" completó la tarea.\n\n${result}`,
					},
				],
				details: {},
			};
		},
	});

	// 2. subagentChain(agent, tasks) — dependent tasks (output N → input N+1)
	pi.registerTool({
		name: "subagentChain",
		label: "Subagent Chain",
		description:
			"Ejecuta una cola dependiente de tareas y espera cada resultado antes de pasar a la siguiente. El output de cada tarea se pasa como contexto a la próxima. Llamá de nuevo con tareas nuevas para seguir la misma cadena (el contexto acumulado se conserva mientras uses el mismo agente).",
		parameters: Type.Object({
			agent: Type.String({ description: "Nombre del agente: scout, planner, writer, reviewer, builder, custom" }),
			tasks: Type.Array(Type.String(), {
				description: "Lista de tareas en orden dependiente",
				minItems: 1,
			}),
		}),
		execute: async (_toolCallId, params, _signal, onUpdate, ctx) => {
			const agentName = params.agent as string;
			const tasks = params.tasks as string[];

			if (tasks.length === 0) {
				return {
					content: [{ type: "text", text: "Error: tasks array must have at least one item." }],
					details: {},
				};
			}

			const agent = loadAgent(agentName);
			const priorContext = chainState && chainState.agent === agentName ? chainState.context : "";
			const priorCompleted = chainState && chainState.agent === agentName ? chainState.completedCount : 0;

			const outcome = await serialize(async () => {
				const sections: string[] = [];
				let context = priorContext;
				let processed = 0;
				let truncated = false;

				for (const task of tasks) {
					const text = await runSubagentTurn(ctx, agentName, task, context || undefined);
					sections.push(`### Tarea ${priorCompleted + processed + 1}: ${task}\n\n${text}`);

					const updated = buildChainContext(context, priorCompleted + processed, text);
					processed += 1;

					if (updated === null) {
						sections.push(
							`⚠️ El contexto acumulado superó ${MAX_CONTEXT_CHARS} caracteres. Se detuvo la cadena acá — si seguís, pasá el contexto necesario a mano.`,
						);
						truncated = true;
						break;
					}
					context = updated;
					onUpdate?.({ content: [{ type: "text", text: sections.join("\n\n---\n\n") }], details: {} });
				}

				return { sections, context, processed, truncated };
			});

			chainState = {
				agent: agentName,
				context: outcome.context,
				completedCount: priorCompleted + outcome.processed,
			};

			return {
				content: [
					{
						type: "text",
						text: `✅ Chain con "${agent.displayName}" — ${outcome.processed}/${tasks.length} tarea(s) ejecutada(s).\n\n${outcome.sections.join("\n\n---\n\n")}`,
					},
				],
				details: {},
			};
		},
	});

	// 3. subagentSeries(agent, tasks) — independent sequential tasks
	pi.registerTool({
		name: "subagentSeries",
		label: "Subagent Series",
		description:
			"Ejecuta tareas independientes en secuencia con el mismo agente, esperando cada una antes de arrancar la siguiente. Cada tarea corre desde cero, sin contexto de las anteriores.",
		parameters: Type.Object({
			agent: Type.String({ description: "Nombre del agente: scout, planner, writer, reviewer, builder, custom" }),
			tasks: Type.Array(Type.String(), {
				description: "Lista de tareas independientes en orden",
				minItems: 1,
			}),
		}),
		execute: async (_toolCallId, params, _signal, onUpdate, ctx) => {
			const agentName = params.agent as string;
			const tasks = params.tasks as string[];

			if (tasks.length === 0) {
				return {
					content: [{ type: "text", text: "Error: tasks array must have at least one item." }],
					details: {},
				};
			}

			const agent = loadAgent(agentName);

			const sections = await serialize(async () => {
				const out: string[] = [];
				for (const [i, task] of tasks.entries()) {
					const text = await runSubagentTurn(ctx, agentName, task);
					out.push(`### Tarea ${i + 1}: ${task}\n\n${text}`);
					onUpdate?.({ content: [{ type: "text", text: out.join("\n\n---\n\n") }], details: {} });
				}
				return out;
			});

			return {
				content: [
					{
						type: "text",
						text: `✅ Series con "${agent.displayName}" — ${tasks.length} tarea(s) ejecutada(s).\n\n${sections.join("\n\n---\n\n")}`,
					},
				],
				details: {},
			};
		},
	});

	// 4. subagentVariants(agent, tasks, continue) — exploration variants
	pi.registerTool({
		name: "subagentVariants",
		label: "Subagent Variants",
		description:
			"Genera múltiples variantes para explorar opciones, esperando cada una. Cada variante es independiente. Usa continue: true para etiquetar una iteración sobre variantes ya mostradas.",
		parameters: Type.Object({
			agent: Type.String({ description: "Nombre del agente: scout, planner, writer, reviewer, builder, custom" }),
			tasks: Type.Array(Type.String(), {
				description: "Lista de variantes a generar",
				minItems: 1,
			}),
			continue: Type.Boolean({
				description: "Si true, marca esta llamada como iteración sobre variantes existentes (solo etiqueta la respuesta)",
				default: false,
			}),
		}),
		execute: async (_toolCallId, params, _signal, onUpdate, ctx) => {
			const agentName = params.agent as string;
			const tasks = params.tasks as string[];
			const continueMode = (params.continue as boolean) ?? false;

			if (tasks.length === 0) {
				return {
					content: [{ type: "text", text: "Error: tasks array must have at least one item." }],
					details: {},
				};
			}

			const agent = loadAgent(agentName);

			const sections = await serialize(async () => {
				const out: string[] = [];
				for (const [i, task] of tasks.entries()) {
					const text = await runSubagentTurn(ctx, agentName, task);
					out.push(`### Variante ${i + 1}: ${task}\n\n${text}`);
					onUpdate?.({ content: [{ type: "text", text: out.join("\n\n---\n\n") }], details: {} });
				}
				return out;
			});

			const modeLabel = continueMode ? "▶️ Iteración de variantes" : "✅ Exploración de variantes";

			return {
				content: [
					{
						type: "text",
						text: `${modeLabel} con "${agent.displayName}" — ${tasks.length} variante(s).\n\n${sections.join("\n\n---\n\n")}`,
					},
				],
				details: {},
			};
		},
	});
}
