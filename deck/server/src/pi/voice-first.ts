import { RINTHEL_PROVIDER_ID } from "./rinthel-provider.js";

/**
 * Voice-first Turns: a prompt sent from voice mode is read aloud, so it carries the `[Audio mode]`
 * marker and one stable system rule tells the model how to speak when it sees it. The first model call
 * of such a Turn skips thinking, so the first spoken words come sooner.
 */
export const AUDIO_MESSAGE_PREFIX = "[Audio mode]\n";
export const VOICE_INSTRUCTIONS = "\n\nThis is a live voice conversation. Start with a short, useful spoken response before any tool calls. For a simple question, answer directly. IMPORTANT: Before every tool call or group of tool calls, first tell the user in a brief, plain spoken sentence what you are about to do. This applies throughout the turn, including subsequent actions after earlier tool results, not only the initial response. Then perform the announced action and continue the work. Do not claim results before checking them. Keep every spoken reply brief: usually one to three short sentences, with only the essential answer or action update. Keep the response short. Use canvas tools for richer, detailed reports, rich Markdown text, detailed explanations, documents, lists, tables, and code that the user should read. When generating a report, write the full report in a canvas and give only a brief spoken summary. Briefly introduce or summarize the canvas in plain speech instead of reading its contents aloud. All user-facing replies in this voice turn, including updates and replies after tools, will be read aloud by text-to-speech. Write plain conversational text in short, clean sentences or simple lines. Do not use Markdown headings, bold, italics, bullet or numbered lists, tables, backticks, code fences, decorative symbols, or Markdown links. Describe steps naturally with words such as first, next, and finally. Avoid raw URLs, long file paths, and command or code dumps in spoken replies; briefly explain the result instead. Write numbers, units, and abbreviations in an easy-to-say form when it improves clarity without changing meaning. Use normal punctuation for natural pauses. These presentation instructions apply only to user-facing speech: keep tool calls, tool arguments, code edits, and generated files in their required formats.";

export const AUDIO_SYSTEM_RULE = "The portal prefixes user requests sent in voice mode with [Audio mode], including microphone transcriptions and typed requests that should receive spoken replies. Decide the reply format from the latest user request only. When it starts with [Audio mode], follow these speaking rules for the entire reply, including updates after tools: " + VOICE_INSTRUCTIONS.trim() + " Do not read the marker aloud. When the latest user request has no [Audio mode] prefix, use normal chat formatting; an audio marker in older conversation history does not keep voice mode enabled.";

/** The `VOICE_*` switches of a voice Turn, read once at boot and handed down. */
export interface VoiceFirstSettings {
  /** Off is the plain baseline: no speaking rules and no audio marker. */
  instructions: boolean;
  /** The first call of a voice Turn skips thinking on the Local model. */
  skipFirstThinking: boolean;
}

export function voiceFirstSettings(env: Record<string, string | undefined>): VoiceFirstSettings {
  return { instructions: env.VOICE_RESPONSE_INSTRUCTIONS !== "false", skipFirstThinking: env.VOICE_SKIP_FIRST_THINKING !== "false" };
}

export function audioSystemRules(settings: VoiceFirstSettings): string[] {
  return settings.instructions ? [AUDIO_SYSTEM_RULE] : [];
}

export function audioMessage(text: string, settings: VoiceFirstSettings): string {
  return settings.instructions ? AUDIO_MESSAGE_PREFIX + text : text;
}

/** The thinking skip is per Turn; the formatting is the system rule's. */
export class VoiceFirstTurn {
  private active = false;
  private first = false;

  constructor(private readonly settings: VoiceFirstSettings) {}

  /** A voice Turn starts; `first` is false when it queues behind a run in course. */
  arm(first = true): void { this.active = true; this.first = first; }
  reset(): void { this.active = false; this.first = false; }

  extension = (pi: any): void => {
    pi.on("before_provider_request", (event: any, ctx: any) => {
      if (!this.settings.skipFirstThinking || !this.active || !this.first) return;
      if (ctx.model?.provider !== RINTHEL_PROVIDER_ID) return;
      const payload = { ...event.payload, chat_template_kwargs: { ...event.payload.chat_template_kwargs, enable_thinking: false } };
      delete payload.thinking_budget_tokens;
      return payload;
    });
    pi.on("turn_end", () => { this.first = false; });
    pi.on("agent_end", () => this.reset());
  };
}
