/**
 * How every inline tool of Deck shows itself to pi: its label is its name in words (labels are never
 * shown in Deck's UI, so they are not translated), and a text answer is pi's text result.
 */

/** The label of a tool: its name with spaces, `rinthel_host_exec` -> `rinthel host exec`. */
export const toolLabel = (name: string): string => name.replaceAll("_", " ");

/** A tool result made of one text part, plus the details the transcript keeps. */
export const textResult = (text: string, details: Record<string, unknown> = {}) => ({ content: [{ type: "text" as const, text }], details });
