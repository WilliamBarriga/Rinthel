/** Persist the guard's decision in the conversation, including across compaction. */
const ENTRY_TYPE = "pithagoras:guard-taint";
const UNTRUSTED_COMMAND = /\b(himalaya|mutt|neomutt|notmuch|offlineimap|mbsync|curl|wget|lynx|w3m)\b/;
const SUBAGENT_TOOLS = new Set(["subagent", "subagentChain", "subagentSeries", "subagentVariants"]);
const ENVELOPE = /<<<\/?untrusted:[0-9a-f]{1,32}>>>/i;

type Result = { toolName?: string; input?: Record<string, unknown>; isError?: boolean };

function untrusted(result: Result): boolean {
  if (result.isError) return false;
  const name = result.toolName ?? "";
  const source = name === "bash" || name === "rinthel_host_exec"
    ? String(result.input?.command ?? "")
    : name;
  return UNTRUSTED_COMMAND.test(source) || /^mcp(_|$)/.test(source) || SUBAGENT_TOOLS.has(name);
}

/** One interface for live results and reconstruction from persisted entries. */
export class SessionTaint {
  private tainted = true;

  constructor(private readonly persist: () => void) {}

  isTainted(): boolean { return this.tainted; }

  observe(result: Result): boolean {
    if (!untrusted(result)) return false;
    if (!this.tainted) {
      // Remain blocked even if the SDK reports a storage error to the user.
      this.tainted = true;
      this.persist();
    }
    return true;
  }

  restore(entries: readonly any[]): void {
    this.tainted = true;
    const calls = new Map<string, Record<string, unknown>>();
    for (const entry of entries) {
      if (entry.type === "custom" && entry.customType === ENTRY_TYPE) {
        this.tainted = true;
        return;
      }
      const message = entry.type === "message" ? entry.message : undefined;
      if (!message) continue;
      if (message.role === "assistant") {
        for (const block of message.content ?? []) {
          if (block.type === "toolCall") calls.set(block.id, block.arguments ?? {});
        }
      } else if (message.role === "toolResult") {
        const result = { ...message, input: calls.get(message.toolCallId) };
        const marked = (message.content ?? []).some((block: any) =>
          block.type === "text" && typeof block.text === "string" && ENVELOPE.test(block.text),
        );
        if (marked || untrusted(result)) {
          this.tainted = true;
          this.persist();
          return;
        }
      }
    }
    this.tainted = false;
  }

  static readonly entryType = ENTRY_TYPE;
}
