import { expect, it } from "vitest";
import { displayPhase, holdsOutput, idleTurn, turnAfter, type TurnState } from "./hands-free-turn";

const quiet = { speaking: false, agentRunning: false };
const run = (state: TurnState, ...events: Parameters<typeof turnAfter>[1][]) => events.reduce(turnAfter, state);

it("starts listening, and a stopped turn ignores every event", () => {
  expect(displayPhase(idleTurn, quiet)).toBe("Escuchando");
  const stopped = turnAfter(idleTurn, { type: "stop" });
  expect(run(stopped, { type: "speech-start" }, { type: "transcribe-start" }, { type: "compacting", active: true })).toBe(stopped);
});

it("the display phase picks the most urgent thing: hearing, compacting, transcribing, speaking, thinking", () => {
  const working = run(idleTurn, { type: "transcribe-start" });
  expect(displayPhase(working, { speaking: true, agentRunning: true })).toBe("Transcribiendo");
  expect(displayPhase(run(working, { type: "compacting", active: true }), quiet)).toBe("Compactando el contexto");
  expect(displayPhase(run(working, { type: "speech-start" }), quiet)).toBe("Te escucho");
  expect(displayPhase(idleTurn, { speaking: true, agentRunning: true })).toBe("Hablando");
  expect(displayPhase(idleTurn, { speaking: false, agentRunning: true })).toBe("Pensando");
  expect(displayPhase(run(idleTurn, { type: "transcribe-start" }, { type: "send-start" }), quiet)).toBe("Pensando");
});

it("a send in flight returns to transcribing, then to idle when the work ends", () => {
  const sending = run(idleTurn, { type: "transcribe-start" }, { type: "send-start" });
  expect(sending.work).toBe("sending");
  expect(run(sending, { type: "send-end" }).work).toBe("transcribing");
  expect(run(sending, { type: "send-end" }, { type: "transcribe-end" }).work).toBe("idle");
});

it("speaking while compacting is remembered apart from hearing, and ends without a turn", () => {
  const compacting = run(idleTurn, { type: "compacting", active: true });
  const over = run(compacting, { type: "speech-start" });
  expect(over.input).toBe("over-compaction");
  expect(displayPhase(over, quiet)).toBe("Compactando el contexto");
  const ended = turnAfter(over, { type: "speech-end" });
  expect(ended.input).toBe("idle");
  expect(ended.takesTurn).toBe(false);
});

it("speech that ends outside compaction takes a turn", () => {
  const hearing = run(idleTurn, { type: "speech-start" });
  expect(hearing.input).toBe("hearing");
  const ended = turnAfter(hearing, { type: "speech-end" });
  expect(ended).toMatchObject({ input: "idle", takesTurn: true });
});

it("muting drops hearing but not the work in progress", () => {
  const busy = run(idleTurn, { type: "transcribe-start" }, { type: "speech-start" });
  const muted = turnAfter(busy, { type: "mute" });
  expect(muted).toMatchObject({ input: "idle", work: "transcribing" });
});

it("output is held only while a sequential, non-sentence run is still working", () => {
  expect(holdsOutput({ sequential: true, sentenceChunks: false }, true)).toBe(true);
  expect(holdsOutput({ sequential: true, sentenceChunks: false }, false)).toBe(false);
  expect(holdsOutput({ sequential: true, sentenceChunks: true }, true)).toBe(false);
  expect(holdsOutput({ sequential: false, sentenceChunks: false }, true)).toBe(false);
  expect(holdsOutput({}, true)).toBe(false);
});
