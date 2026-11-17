import { expect, it } from "vitest";
import { newUserErrors, passwordError, userPatch } from "./user-form";

const ANA = { id: 2, username: "ana", role: "miembro" as const, notes: "", created_at: "2026-10-01T08:00:00Z", disabled: false };

it("the password minimum counts code points, and an empty one is only fine when optional", () => {
  expect(passwordError("")).toMatch(/Escribe/);
  expect(passwordError("", true)).toBeUndefined();
  expect(passwordError("1234567")).toMatch(/8 caracteres/);
  expect(passwordError("ñandú-ok")).toBeUndefined();
});

it("the patch carries only what changed; an untouched panel saves nothing", () => {
  expect(userPatch(ANA, { role: "miembro", notes: "", password: "" })).toEqual({});
  expect(userPatch(ANA, { role: "admin", notes: "x", password: "nueva-clave" })).toEqual({ role: "admin", notes: "x", password: "nueva-clave" });
});

it("a new user needs a name and a valid password", () => {
  expect(newUserErrors({ username: " ", password: "" })).toEqual({ username: "Escribe un nombre.", password: "Escribe una contraseña." });
  expect(newUserErrors({ username: "dora", password: "dora-password" })).toEqual({});
});
