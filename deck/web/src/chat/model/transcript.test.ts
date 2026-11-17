import { expect, it } from "vitest";
import type { SessionEvent } from "@deck/contract";
import { emptyTranscript, foldEvent, windowLabel, type Transcript } from "./transcript";

const fold = (events: (SessionEvent | { type: "live-reset" })[], from: Transcript = emptyTranscript) => events.reduce(foldEvent, from);
let seq = 0;
const stored = (type: string, payload: unknown): SessionEvent => ({ seq: ++seq, type, payload });
const live = (type: string, payload: unknown): SessionEvent => ({ seq: -(++seq), type, payload });

it("a turn reads as the person's message, the streamed answer, then the final one", () => {
  const streaming = fold([
    stored("portal_prompt", { message: "hola", turn_id: "t1" }),
    stored("portal_status", { status: "running" }),
    live("portal_prefill", { total: 100, cache: 60, processed: 40, timeMs: 10 }),
    live("message_update", { streamId: "s1", assistantMessageEvent: { type: "thinking_delta", delta: "pienso" } }),
    live("message_update", { streamId: "s1", assistantMessageEvent: { type: "text_delta", delta: "ho" } }),
    live("message_update", { streamId: "s1", assistantMessageEvent: { type: "text_delta", delta: "la" } }),
  ]);
  expect(streaming.status).toBe("running");
  expect(streaming.prefill).toBeNull();
  expect(streaming.items).toEqual([
    { kind: "user", id: "t1", text: "hola" },
    { kind: "assistant", id: "s1", text: "hola", thinking: "pienso", streaming: true },
  ]);
  const done = fold([
    stored("message_end", { streamId: "s1", message: { role: "assistant", content: [{ type: "thinking", thinking: "pienso" }, { type: "text", text: "hola!" }] } }),
    stored("agent_settled", {}),
    stored("portal_status", { status: "idle" }),
  ], streaming);
  expect(done.items[1]).toEqual({ kind: "assistant", id: "s1", text: "hola!", thinking: "pienso", streaming: false });
  expect(done.status).toBe("idle");
});

it("prefill progress shows while llama reads the prompt, and the route says the model and its window", () => {
  const state = fold([
    live("portal_route", { model: "qwen-a", context_window: 65536 }),
    live("portal_prefill", { total: 100, cache: 60, processed: 40, timeMs: 10 }),
  ]);
  expect(state.prefill).toEqual({ total: 100, cache: 60, processed: 40, timeMs: 10 });
  expect(state.route).toEqual({ model: "qwen-a", contextWindow: 65536 });
});

it("a stored event replayed again is folded once; live events never move the cursor", () => {
  const first = stored("portal_prompt", { message: "uno", turn_id: "a" });
  const state = fold([first, live("portal_prefill", { total: 1, cache: 0, processed: 0, timeMs: 0 }), first]);
  expect(state.items).toHaveLength(1);
  expect(state.lastSeq).toBe(first.seq);
});

it("a live reset drops what was only streaming; the snapshot after it brings it back", () => {
  const state = fold([
    live("message_update", { streamId: "s9", assistantMessageEvent: { type: "text_delta", delta: "a medias" } }),
    { type: "live-reset" },
  ]);
  expect(state.items).toEqual([]);
  const back = fold([live("message_snapshot", { streamId: "s9", message: { content: [{ type: "text", text: "a medias" }] } })], state);
  expect(back.items[0]).toMatchObject({ kind: "assistant", text: "a medias", streaming: true });
});

it("tools, the Guard's refusals, notices and a failed turn reach the transcript", () => {
  const state = fold([
    stored("tool_execution_start", { toolCallId: "c1", toolName: "bash", args: { command: "ls" } }),
    stored("tool_execution_end", { toolCallId: "c1", toolName: "bash", isError: false, result: { content: [{ type: "text", text: "a.txt" }] } }),
    stored("portal_guard", { tool: "bash", verdict: "deny", reason: "publish: pushing" }),
    stored("message_end", { message: { role: "assistant", content: [], stopReason: "error", errorMessage: "No hay un Local model activo" } }),
    stored("portal_status", { status: "error", error: "pi terminó" }),
  ]);
  expect(state.items.map((i) => i.kind)).toEqual(["tool", "guard", "notice", "notice"]);
  expect(state.items[0]).toMatchObject({ name: "bash", detail: "ls", status: "done", output: "a.txt" });
  expect(state.items[2]).toMatchObject({ text: "No hay un Local model activo", error: true });
});

it("an extension's dialog waits until answered or cancelled", () => {
  const asked = fold([live("extension_ui_request", { id: "d1", method: "confirm", title: "¿Seguro?", message: "borrar" })]);
  expect(asked.dialogs).toEqual([{ id: "d1", method: "confirm", title: "¿Seguro?", message: "borrar", options: undefined }]);
  expect(fold([live("extension_ui_cancel", { id: "d1" })], asked).dialogs).toEqual([]);
});

it("the window label reads the Local model's window, with what is used when known", () => {
  expect(windowLabel(null, null)).toBeNull();
  expect(windowLabel(null, 65536)).toBe("66k de contexto");
  expect(windowLabel(12_345, 65536)).toBe("12k / 66k");
  expect(windowLabel(900, 8192)).toBe("900 / 8.2k");
});
