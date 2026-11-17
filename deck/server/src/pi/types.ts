import type { EventEmitter } from "node:events";
import type { ToolProfile } from "../tool-profile.js";

export interface PiState {
  model: { id: string; name: string; provider: string; contextWindow?: number };
  thinkingLevel: string;
  autoCompactionEnabled?: boolean;
  messageCount?: number;
}

export interface PiStats {
  tokens: { input: number; output: number; cacheRead?: number; cacheWrite?: number; total: number };
  contextUsage: { tokens: number; contextWindow: number; percent: number };
  toolCalls: number;
  totalMessages: number;
}

export interface PiCommand {
  name: string;
  description?: string;
  source: string;
}

/**
 * What Deck needs from a Session's pi. One implementation runs it (`SdkPiClient`, pi's SDK in this
 * process); the tests drive the `SessionManager` with a double.
 *
 * Events go out as `event` (pi's own, plus the Guard's `portal_guard` and `portal_notice`), and the end
 * of the client as `exit`.
 */
export interface PiClient extends EventEmitter {
  readonly running: boolean;
  /** pi's session file, once written: recorded so the same conversation is reopened after a restart. */
  readonly sessionFile?: string;
  /** What the Session's Agent was launched with. */
  readonly profile: ToolProfile;

  /** Resolves once pi has taken the message (started, queued); the run goes on and reports through events. */
  prompt(message: string): Promise<void>;
  abort(): Promise<void>;
  /** Whether the agent has stopped for good, not merely between turns. */
  isIdle(): boolean;
  dispose(): void;

  getState(): Promise<PiState>;
  getStats(): Promise<PiStats>;
  getThinkingLevels(): Promise<string[]>;
  getCommands(): Promise<PiCommand[]>;
  setThinkingLevel(level: string): Promise<void>;
  compact(): Promise<void>;

  /** Answers an extension dialog. False when the request is unknown or expired. */
  respondUi(id: string, response: { cancelled?: boolean; value?: unknown }): boolean;
}
