import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import type { ModelAccess } from "../../session-proxy.js";
import { discoverAgents } from "./agents.js";
import { runChild, type ChildResult, type ChildTool } from "./child.js";

/**
 * `subagent`: an admin's Agent hands a task to a child with a context of its own (`child.ts`), one
 * child at a time per Session (the Instance has one Local model). See `docs/deck/architecture.md`.
 *
 *   single: { agent, task }
 *   chain:  { chain: [{ agent, task }] }   each step gets the previous answer as {previous}
 *   tasks:  { tasks: [{ agent, task }] }   independent, one after another (variants: true = alternatives)
 *
 * Optional: skills (for all or per item), persona (the role for this task), inlineSkills.
 *
 * - Admin only, checked twice: loaded only in an admin's Session (`ToolProfile`), and every call asks
 *   again whether the owner is an admin now; no answer is a no.
 * - The child's answer is untrusted: it taints the Session (`SUBAGENT_TOOLS` in `session-taint.ts`),
 *   and a tainted Session loses the tool (`TAINT_REVOKED_TOOLS` in `guard.ts`).
 */

export const SUBAGENT_TOOL = "subagent";

const MAX_TASKS = 8;
const OUTPUT_CAP = 50 * 1024;

export interface SubagentOptions {
  /** The parent Deck Session. */
  sessionId: string;
  /** Deck's agentDir: its `agents/*.md` join the image's, its `skills/` are found by name. */
  agentDir: string;
  /** The parent's way to its model, shared by every child. */
  modelAccess: ModelAccess;
  /** Whether the Session's owner is an admin right now: asked before every call. */
  adminNow: () => Promise<boolean>;
  /** What a child gets beyond pi's built-ins and the agentDir (`ChildTool`). */
  childTools: readonly ChildTool[];
  /** Where the agent types the volume replaces are told. */
  log?: (line: string) => void;
}

const Item = Type.Object({
  agent: Type.String({ description: "Agent name" }),
  task: Type.String({ description: "The task. In a chain, {previous} is the previous step's answer" }),
  skills: Type.Optional(Type.Array(Type.String(), { description: "Extra skills for this item only" })),
  persona: Type.Optional(Type.String({ description: "Role for this item (useful with the custom agent)" })),
});

const Params = Type.Object({
  agent: Type.Optional(Type.String({ description: "Single mode: agent name" })),
  task: Type.Optional(Type.String({ description: "Single mode: the task" })),
  chain: Type.Optional(Type.Array(Item, { description: "Dependent steps, in order" })),
  tasks: Type.Optional(Type.Array(Item, { description: "Independent tasks, run one after another" })),
  variants: Type.Optional(Type.Boolean({ description: "With tasks: they are alternatives to compare" })),
  skills: Type.Optional(Type.Array(Type.String(), { description: "Skills for every item" })),
  persona: Type.Optional(Type.String({ description: "Persona for every item" })),
  inlineSkills: Type.Optional(Type.Boolean({ description: "Paste the whole SKILL.md instead of loading it on demand" })),
});

type Item = { agent: string; task: string; skills?: string[]; persona?: string };

const cap = (text: string) => (text.length > OUTPUT_CAP ? `${text.slice(0, OUTPUT_CAP)}\n\n[truncated]` : text);

export interface SubagentDetails {
  mode: "single" | "chain" | "tasks";
  results: ChildResult[];
}

/** An ExtensionFactory (pi's inline extension), one instance per admin Session. */
export function subagentExtension(opts: SubagentOptions) {
  const log = opts.log ?? ((line: string) => console.log(line));

  /** One child at a time in this Session, even if pi runs two calls side by side. */
  let queue: Promise<unknown> = Promise.resolve();
  const oneAtATime = <T>(fn: () => Promise<T>): Promise<T> => {
    const run = queue.then(fn, fn);
    queue = run.then(() => undefined, () => undefined);
    return run;
  };

  async function requireAdmin(): Promise<void> {
    let admin = false;
    try {
      admin = await opts.adminNow();
    } catch {
      admin = false;
    }
    if (!admin) throw new Error("Refused: subagents are for an admin, and the owner of this Session is not one now (or that could not be checked).");
  }

  return async (pi: ExtensionAPI): Promise<void> => {
    // The catalog in the description is read once; each call reads the agents again, quietly.
    const catalog = (await discoverAgents(opts.agentDir, log)).map((a) => `${a.name}: ${a.description}`).join(" | ");

    pi.registerTool({
      name: SUBAGENT_TOOL,
      label: "Subagent",
      description:
        "Delegate work to subagents, each with its own isolated context. They run one at a time (local model). " +
        "Modes: single (agent+task), chain (steps with {previous}), tasks (independent; variants:true for alternatives). " +
        "Their answer counts as untrusted content. " +
        `Agents: ${catalog}.`,
      parameters: Params,

      async execute(_id: string, params: any, signal: AbortSignal | undefined, onUpdate: any, ctx: any) {
        await requireAdmin();
        const agents = await discoverAgents(opts.agentDir);
        const mode: SubagentDetails["mode"] = params.chain?.length ? "chain" : params.tasks?.length ? "tasks" : "single";
        const items: Item[] =
          mode === "chain" ? params.chain : mode === "tasks" ? params.tasks : params.agent && params.task ? [{ agent: params.agent, task: params.task }] : [];
        const fail = (text: string) => ({ content: [{ type: "text" as const, text }], details: { mode, results: [] } as SubagentDetails, isError: true });

        if (items.length === 0) return fail(`Missing agent+task, chain or tasks. Agents: ${agents.map((a) => a.name).join(", ")}`);
        if (items.length > MAX_TASKS) return fail(`Too many items (${items.length}); at most ${MAX_TASKS}.`);
        const unknown = items.find((i) => !agents.some((a) => a.name === i.agent));
        if (unknown) return fail(`Unknown agent "${unknown.agent}". Available: ${agents.map((a) => a.name).join(", ")}`);

        const results: ChildResult[] = [];
        // Once a child ran, its words are in the answer even when it failed: never an error result,
        // because the taint does not count a failed call as untrusted.
        const answer = (text: string) => ({ content: [{ type: "text" as const, text: text || "(no output)" }], details: { mode, results } as SubagentDetails });
        let previous = "";
        for (const [index, item] of items.entries()) {
          const agent = agents.find((a) => a.name === item.agent)!;
          const task = mode === "chain" && index > 0 ? item.task.replaceAll("{previous}", previous) : item.task;
          const result = await oneAtATime(() =>
            runChild(agent, task, {
              sessionId: opts.sessionId,
              cwd: ctx?.cwd ?? process.cwd(),
              agentDir: opts.agentDir,
              modelAccess: opts.modelAccess,
              childTools: opts.childTools,
              thinking: ctx?.thinkingLevel,
              skills: [...(params.skills ?? []), ...(item.skills ?? [])],
              inlineSkills: params.inlineSkills ?? false,
              persona: item.persona ?? params.persona,
              signal,
              onProgress: (partial) =>
                onUpdate?.({ content: [{ type: "text", text: partial.output || "(running...)" }], details: { mode, results: [...results, partial] } }),
            }),
          );
          results.push(result);
          previous = cap(result.output);
          if (!result.ok && mode === "chain") {
            return answer(`Chain stopped at step ${results.length} (${item.agent}): ${result.output}`);
          }
        }

        const text =
          mode === "single"
            ? cap(results[0].output)
            : mode === "chain"
              ? cap(results[results.length - 1].output)
              : results
                  .map((r, i) => `### ${params.variants ? "Variant" : "Task"} ${i + 1} [${r.agent}] ${r.ok ? "ok" : "failed"}\n\n${cap(r.output)}`)
                  .join("\n\n---\n\n");
        return answer(text);
      },
    } as any);
  };
}
