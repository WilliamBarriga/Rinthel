/**
 * Ejecuta UN subagente en su propia AgentSession (mismo proceso, sin arranque de `pi`).
 * Un lock global asegura un subagente a la vez: el modelo local tiene un solo slot.
 */

import {
	createAgentSession,
	DefaultResourceLoader,
	getAgentDir,
	SessionManager,
} from "@earendil-works/pi-coding-agent";
import type { Agent } from "./agents.ts";
import { resolveSkills } from "./skills.ts";

/**
 * Tools que un subagente nunca usa: memoria solo con permiso de Tarkark, no hay UI para preguntar,
 * y el guard de Pithagoras no corre en la sesion hija, asi que nada con alcance sobre el host.
 */
const EXCLUDED_TOOLS = [
	"mcp__understory__memory_add",
	"mcp__understory__memory_update",
	"mcp__understory__memory_maintain",
	"ask_user_question",
	"rinthel_host_exec",
	"subagent",
];

/** La sesion hija carga los paquetes instalados; estas extensiones no deben cargarse ahi (sin sub-subagentes, sin host exec). */
const CHILD_BLOCKED_TOOLS = ["subagent", "rinthel_host_exec"];

export interface Result {
	agent: string;
	task: string;
	ok: boolean;
	output: string; // ultimo texto del asistente (o el error)
	toolCalls: string[]; // nombres de tools usadas, para mostrar progreso
	turns: number;
	tokens: { input: number; output: number };
	skills: string[];
}

export interface RunOptions {
	cwd: string;
	model: unknown; // Model de la sesion principal
	thinking?: string;
	skills: string[];
	inlineSkills: boolean;
	persona?: string;
	signal?: AbortSignal;
	onProgress?: (partial: Result) => void;
}

let queueTail: Promise<unknown> = Promise.resolve();
function serialize<T>(fn: () => Promise<T>): Promise<T> {
	const run = queueTail.then(fn, fn);
	queueTail = run.then(() => undefined, () => undefined);
	return run;
}

export function runAgent(agent: Agent, task: string, opts: RunOptions): Promise<Result> {
	return serialize(() => run(agent, task, opts));
}

async function run(agent: Agent, task: string, opts: RunOptions): Promise<Result> {
	const skills = resolveSkills([...agent.skills, ...opts.skills], opts.cwd, opts.inlineSkills);
	const result: Result = {
		agent: agent.name,
		task,
		ok: true,
		output: "",
		toolCalls: [],
		turns: 0,
		tokens: { input: 0, output: 0 },
		skills: skills.names,
	};
	const prompt = [skills.inlined, agent.prompt, opts.persona ? `## Persona para esta tarea\n${opts.persona}` : ""]
		.filter(Boolean)
		.join("\n\n");

	let session: Awaited<ReturnType<typeof createAgentSession>>["session"] | undefined;
	let stopReason = "";
	const stop = (reason: string) => {
		stopReason ||= reason;
		void session?.abort();
	};
	const onAbort = () => stop("aborted");
	let timer: ReturnType<typeof setTimeout> | undefined;
	let unsubscribe: (() => void) | undefined;

	try {
		const loader = new DefaultResourceLoader({
			cwd: opts.cwd,
			agentDir: getAgentDir(),
			appendSystemPrompt: [prompt],
			noSkills: true, // solo las skills pedidas, para no gastar contexto
			additionalSkillPaths: skills.dirs,
			noPromptTemplates: true,
			noThemes: true,
			// Sin estado global (Pithagoras corre varias sesiones en un proceso): se filtra por las tools que registran.
			extensionsOverride: (base) => ({
				...base,
				extensions: base.extensions.filter((e) => !CHILD_BLOCKED_TOOLS.some((t) => e.tools.has(t))),
			}),
		});
		await loader.reload();
		session = (
			await createAgentSession({
				cwd: opts.cwd,
				model: opts.model as never,
				thinkingLevel: (agent.thinking ?? opts.thinking) as never,
				tools: agent.tools,
				excludeTools: EXCLUDED_TOOLS,
				resourceLoader: loader,
				sessionManager: SessionManager.inMemory(opts.cwd),
			})
		).session;

		unsubscribe = session.subscribe((event) => {
			if (event.type !== "message_end" || event.message.role !== "assistant") return;
			const msg = event.message;
			result.turns++;
			result.tokens.input += msg.usage?.input ?? 0;
			result.tokens.output += msg.usage?.output ?? 0;
			for (const part of msg.content) {
				if (part.type === "text") result.output = part.text;
				else if (part.type === "toolCall") result.toolCalls.push(part.name);
			}
			if (msg.errorMessage) stopReason ||= msg.errorMessage;
			if (result.turns >= agent.maxTurns) stop(`max turns ${agent.maxTurns}`);
			opts.onProgress?.({ ...result });
		});
		timer = setTimeout(() => stop(`timeout ${agent.timeoutSec}s`), agent.timeoutSec * 1000);
		if (opts.signal?.aborted) onAbort();
		else opts.signal?.addEventListener("abort", onAbort, { once: true });

		await session.prompt(`Task: ${task}`);
	} catch (err) {
		stopReason ||= String((err as Error)?.message ?? err);
	} finally {
		if (timer) clearTimeout(timer);
		opts.signal?.removeEventListener("abort", onAbort);
		unsubscribe?.();
		session?.dispose();
	}

	if (stopReason) {
		result.ok = false;
		result.output = result.output ? `${result.output}\n\n[${stopReason}]` : `Subagent failed: ${stopReason}`;
	}
	if (skills.missing.length > 0) result.output += `\n\n(skills no encontradas: ${skills.missing.join(", ")})`;
	return result;
}
