import { describe, expect, it } from "vitest";
import type { Branding, Personalization } from "@deck/contract";
import { defaultBranding, defaultPreferences } from "../../../shared/appearance.mjs";
import { fetchAppearanceApi } from "./adapters/fetch-appearance";
import { fakeAppearanceApi } from "./fakes/appearance";
import type { AppearanceApi } from "./appearance";

const config = (over: Partial<Personalization["preferences"]> = {}): Personalization => ({ version: 1, preferences: { ...defaultPreferences, density: "compact", ...over }, profiles: [] });

/** A stand-in for Deck's `/api/appearance`, written from its rules: a member keeps the shared colors and cannot change the brand. */
function deckAppearance(isAdmin: boolean): typeof fetch {
  let personal: Personalization | null = null;
  let branding: Branding = { ...defaultBranding };
  return (async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = new URL(String(input), "http://deck").pathname;
    if (path === "/api/appearance" && init?.method !== "PUT") return Response.json({ personal, branding });
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    if (path === "/api/appearance") {
      if (!isAdmin && body.preferences.theme !== defaultPreferences.theme) return Response.json({ error: "Los colores y el tema los administra el administrador." }, { status: 403 });
      personal = body;
      return Response.json(personal);
    }
    if (path === "/api/appearance/brand") {
      if (!isAdmin) return Response.json({ error: "Solo el administrador puede cambiar la marca de instalación." }, { status: 403 });
      branding = body;
      return Response.json(branding);
    }
    return Response.json({ error: "No such route" }, { status: 404 });
  }) as typeof fetch;
}

function contract(name: string, open: (isAdmin: boolean) => AppearanceApi) {
  describe(`AppearanceApi: ${name}`, () => {
    it("starts with factory values, and what a person saves is read back", async () => {
      const api = open(false);
      expect((await api.appearance()).personal).toBeNull();
      await api.saveAppearance(config());
      expect((await api.appearance()).personal?.preferences.density).toBe("compact");
    });

    it("a member cannot change the shared colors or the brand (403) and keeps what they had", async () => {
      const api = open(false);
      await api.saveAppearance(config());
      await expect(api.saveAppearance(config({ theme: "cyberpunk" }))).rejects.toMatchObject({ status: 403 });
      await expect(api.saveBranding({ ...defaultBranding, name: "Mía" })).rejects.toMatchObject({ status: 403 });
      expect((await api.appearance()).personal?.preferences.theme).toBe("system");
      expect((await api.appearance()).branding.name).toBe("Rinthel.Ai");
    });

    it("the admin saves the brand and everyone reads it", async () => {
      const api = open(true);
      expect((await api.saveBranding({ ...defaultBranding, name: "Mi Instance" })).name).toBe("Mi Instance");
      expect((await api.appearance()).branding.name).toBe("Mi Instance");
    });
  });
}

contract("fake", (isAdmin) => fakeAppearanceApi({ isAdmin }));
contract("fetch adapter", (isAdmin) => fetchAppearanceApi(deckAppearance(isAdmin)));
