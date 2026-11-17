import { expect, it } from "vitest";
import { initialVoiceSession, voiceSessionReducer } from "./voice-session";

it("voice cannot become active without starting, or from a late completion after stopping", () => {
  expect(voiceSessionReducer(initialVoiceSession, { type: "started" })).toBe(initialVoiceSession);
  const starting = voiceSessionReducer(initialVoiceSession, { type: "start" });
  expect(voiceSessionReducer(starting, { type: "start" })).toBe(starting);
  const stopped = voiceSessionReducer(starting, { type: "stop" });
  expect(voiceSessionReducer(stopped, { type: "started" })).toBe(stopped);
});

it("stopping while off is rejected and keeps a retained failure", () => {
  expect(voiceSessionReducer(initialVoiceSession, { type: "stop" })).toBe(initialVoiceSession);
  const failed = { ...initialVoiceSession, error: "Microphone disconnected" };
  expect(voiceSessionReducer(failed, { type: "stop" })).toBe(failed);
});

it("ending a voice session resets transient state but retains a failure for the start button", () => {
  const active = voiceSessionReducer(voiceSessionReducer(initialVoiceSession, { type: "start" }), { type: "started" });
  const failed = { ...active, muted: true, speaking: true, transcript: "parcial", error: "Microphone disconnected" };
  const stopped = voiceSessionReducer(Object.freeze(failed), { type: "stop" });
  expect(stopped).toEqual({ ...initialVoiceSession, error: "Microphone disconnected" });
  expect(voiceSessionReducer(stopped, { type: "read", reading: { speaking: true } })).toBe(stopped);
  expect(voiceSessionReducer(stopped, { type: "read", reading: { transcript: "tardía" } })).toBe(stopped);
  expect(voiceSessionReducer(stopped, { type: "start" })).toMatchObject({ status: "starting", error: "" });
});

it("a reading updates only the fields it names while the session lives", () => {
  const active = voiceSessionReducer(voiceSessionReducer(initialVoiceSession, { type: "start" }), { type: "started" });
  const heard = voiceSessionReducer(active, { type: "read", reading: { phase: "Te escucho", transcript: "hola" } });
  expect(heard).toMatchObject({ status: "active", phase: "Te escucho", transcript: "hola", muted: false });
  expect(voiceSessionReducer(heard, { type: "read", reading: { muted: true } })).toMatchObject({ phase: "Te escucho", muted: true });
});

it("an error is kept whether the session is off or running", () => {
  expect(voiceSessionReducer(initialVoiceSession, { type: "error", value: "sin permiso" }).error).toBe("sin permiso");
});
