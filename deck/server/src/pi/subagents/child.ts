import type { ModelAccess } from "../../session-proxy.js";
import { guardExtension, TAINT_REVOKED_TOOLS } from "../guard.js";
import { routedModel, rinthelProviderExtension } from "../rinthel-provider.js";
import { SessionTaint } from "../session-taint.js";
import type { AgentType } from "./agents.js";
import { resolveSkills } from "./skills.js";

/**
 * One child: a pi `AgentSession` in this process, in memory, gone when it answers. It talks to the
 * parent's Local model through the parent's `ModelAccess` (same proxy URL, so it shares and overwrites
 * the Session's slot, one HTTP request at a time), runs with a Guard of its own, and never has what a
 * tainted Session loses (`TAINT_REVOKED_TOOLS`: `subagent`, host exec, Memoria writes) nor a way to ask
 * the person anything.
 */

/** An inline factory a child loads on top of pi's built-ins and the agentDir, with the tools it registers. */
export interface ChildTool {
  name: string;
  /** What it registers: added to an agent's allowlist, so an agent with `tools:` still gets them. */
  tools: readonly string[];
  factory: (pi: any) => void | Promise<void>;
}

/** Never in a child, whatever an agent's `tools:` or an installed package says. */
export const CHILD_EXCLUDED_TOOLS: readonly string[] = [...TAINT_REVOKED_TOOLS, "understory_memory_maintain", "ask_user_question"];

export interface ChildResult {
  agent: string;
  task: string;
  ok: boolean;
  /** The child's last text, or why it stopped. */
  output: string;
  toolCalls: string[];
  turns: number;
  tokens: { input: number; output: number };
  skills: string[];
}

export interface ChildRun {
  /** The parent Deck Session, for the child Guard's log. */
  sessionId: string;
  cwd: string;
  agentDir: string;
  modelAccess: ModelAccess;
  childTools: readonly ChildTool[];
  thinking?: string;
  skills: string[];
  inlineSkills: boolean;
  persona?: string;
  signal?: AbortSignal;
  onProgress?: (partial: ChildResult) => void;
}

/** A child's taint lives as long as the child: nothing to keep. */
function childTaintMarks() {
  let tainted = false;
  return {
    isTainted: async () => tainted,
    markTainted: async () => { tainted = true; },
  };
}

export async function runChild(agent: AgentType, task: string, opts: ChildRun): Promise<ChildResult> {
  // Imported lazily: importing this module must not load pi.
  const pi: any = await import("@earendil-works/pi-coding-agent");
  const skills = resolveSkills([...agent.skills, ...opts.skills], opts.cwd, opts.agentDir, opts.inlineSkills);
  const result: ChildResult = {
    agent: agent.name,
    task,
    ok: true,
    output: "",
    toolCalls: [],
    turns: 0,
    tokens: { input: 0, output: 0 },
    skills: skills.found,
  };
  const prompt = [skills.inlined, agent.prompt, opts.persona ? `## Persona for this task\n${opts.persona}` : ""].filter(Boolean).join("\n\n");
  const excluded = new Set(CHILD_EXCLUDED_TOOLS);

  let session: any;
  let stopReason = "";
  const stop = (reason: string) => {
    stopReason ||= reason;
    void session?.abort();
  };
  const onAbort = () => stop("aborted");
  let timer: ReturnType<typeof setTimeout> | undefined;
  let unsubscribe: (() => void) | undefined;

  try {
    const childId = `${opts.sessionId}/subagent`;
    const loader = new pi.DefaultResourceLoader({
      cwd: opts.cwd,
      agentDir: opts.agentDir,
      extensionFactories: [
        { name: "guard", factory: guardExtension({ sessionId: childId, taint: new SessionTaint(childId, childTaintMarks()) }) },
        { name: "rinthel-provider", factory: rinthelProviderExtension(opts.modelAccess, (model) => session.setModel(model)) },
        ...opts.childTools.map((t) => ({ name: t.name, factory: t.factory })),
      ],
      appendSystemPrompt: [prompt],
      // Only the skills asked for, to spare the context.
      noSkills: true,
      additionalSkillPaths: skills.dirs,
      noPromptTemplates: true,
      noThemes: true,
      // An installed package that registers an excluded tool is not loaded at all.
      extensionsOverride: (base: any) => ({
        ...base,
        extensions: base.extensions.filter((e: any) => ![...(e.tools?.keys?.() ?? [])].some((t: string) => excluded.has(t))),
      }),
    });
    await loader.reload();
    const tools = agent.tools ? [...agent.tools, ...opts.childTools.flatMap((t) => t.tools)] : undefined;
    session = (
      await pi.createAgentSession({
        cwd: opts.cwd,
        agentDir: opts.agentDir,
        resourceLoader: loader,
        sessionManager: pi.SessionManager.inMemory(opts.cwd),
        ...(tools ? { tools } : {}),
        excludeTools: [...excluded],
        ...((agent.thinking ?? opts.thinking) ? { thinkingLevel: agent.thinking ?? opts.thinking } : {}),
      })
    ).session;
    // The Guard rebuilds its taint at session_start, and the provider exists once bound.
    await session.bindExtensions({ mode: "print" });
    await session.setModel(routedModel(opts.modelAccess.url, opts.modelAccess.route()));

    unsubscribe = session.subscribe((event: any) => {
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
    timer.unref?.();
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
  if (skills.missing.length > 0) result.output += `\n\n(skills not found: ${skills.missing.join(", ")})`;
  return result;
}
