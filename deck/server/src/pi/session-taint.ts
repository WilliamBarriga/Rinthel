import type { SessionTaintRepo } from "../store/port.js";
import { SUBAGENT_TOOL } from "./admin-tool.js";

/**
 * A Session's taint: whether it has read somebody else's words. One object for live results and for
 * the rebuild when the Session's pi starts, kept in the store (`SessionTaintRepo`) so a relaunch, a
 * restart of Deck or a lost pi file never starts it clean again.
 *
 * It starts tainted and stays so until `restore` has looked: a call that lands before the rebuild is
 * judged as tainted, and a store that cannot be read leaves it tainted.
 */

/** Commands whose output is somebody else's words: mail, and anything fetched from the network. */
const UNTRUSTED_COMMAND = /\b(himalaya|mutt|neomutt|notmuch|offlineimap|mbsync|curl|wget|lynx|w3m)\b/;

/** A subagent's reads happen out of this Session's sight: its answer may carry them. */
export const SUBAGENT_TOOLS: ReadonlySet<string> = new Set([SUBAGENT_TOOL]);

/** The Guard's envelope, as it stays in a tool result already in the conversation. */
const ENVELOPE = /<<<\/?untrusted:[0-9a-f]{1,32}>>>/i;

/** A tool result as pi hands it to `tool_result`, or as rebuilt from its persisted call. */
export interface ToolOutcome {
  toolName?: string;
  input?: Record<string, unknown>;
  isError?: boolean;
}

export interface SessionTaintOptions {
  /** The browser tools the Session registered for itself: what they read is the open web. */
  browserTools?: ReadonlySet<string>;
}

export class SessionTaint {
  private tainted = true;
  private readonly browserTools: ReadonlySet<string>;

  constructor(
    private readonly sessionId: string,
    private readonly marks: SessionTaintRepo,
    options: SessionTaintOptions = {},
  ) {
    this.browserTools = options.browserTools ?? new Set();
  }

  isTainted(): boolean {
    return this.tainted;
  }

  /** Whether this outcome carries somebody else's words. A failed call carries nothing. */
  untrusted(result: ToolOutcome): boolean {
    if (result.isError) return false;
    const name = result.toolName ?? "";
    const source = name === "bash" || name === "rinthel_host_exec" ? String(result.input?.command ?? "") : name;
    // MCP tools reach servers Deck does not control: their output is someone else's words, like mail.
    return UNTRUSTED_COMMAND.test(source) || /^mcp(_|$)/.test(source) || SUBAGENT_TOOLS.has(name) || this.browserTools.has(name);
  }

  /**
   * Taints the Session if `result` is untrusted, and says whether it was. The running Session is
   * tainted before the mark is written, and stays so if the store fails: the failure is logged, not
   * thrown, so the output is still enveloped.
   */
  async observe(result: ToolOutcome): Promise<boolean> {
    if (!this.untrusted(result)) return false;
    await this.taint();
    return true;
  }

  /** Taints the Session for good: in memory now, in the store as well as it can. */
  async taint(): Promise<void> {
    this.tainted = true;
    try {
      await this.marks.markTainted(this.sessionId);
    } catch (e) {
      console.error(`[guard ${this.sessionId}] could not store the taint mark; the running Session stays tainted:`, e);
    }
  }

  /**
   * The rebuild at `session_start`: the stored mark, or else every entry of pi's file (all of them,
   * not the active branch: compaction or tree navigation must not undo a decision already made). An
   * untrusted result found there is stored as the mark. Clean only when both say so.
   */
  async restore(entries: readonly any[]): Promise<void> {
    this.tainted = true;
    if (await this.marks.isTainted(this.sessionId)) return;
    const calls = new Map<string, Record<string, unknown>>();
    for (const entry of entries) {
      const message = entry?.type === "message" ? entry.message : undefined;
      if (!message) continue;
      if (message.role === "assistant") {
        for (const block of message.content ?? []) {
          if (block?.type === "toolCall") calls.set(block.id, block.arguments ?? {});
        }
      } else if (message.role === "toolResult") {
        const marked = (message.content ?? []).some((block: any) =>
          block?.type === "text" && typeof block.text === "string" && ENVELOPE.test(block.text),
        );
        if (marked || this.untrusted({ ...message, input: calls.get(message.toolCallId) })) {
          await this.taint();
          return;
        }
      }
    }
    this.tainted = false;
  }
}
