import { describe, expect, it } from "vitest";
import type { BrowserStatus } from "@deck/contract";
import type { BrowserApi } from "./browser";
import { fetchBrowserApi } from "./adapters/fetch-browser";
import { fakeBrowserApi } from "./fakes/browser";

/** A stand-in for Deck's `/api/browser` routes, written from their rules (not the fake's code). */
function deckBrowser(role: "admin" | "miembro"): typeof fetch {
  let container: BrowserStatus["install"]["container"] = "absent";
  let hasPassword = false;
  let allowlist = "";
  const sessions: BrowserStatus["sessions"] = [];
  const json = (body: unknown, status = 200) => Response.json(body, { status });
  return (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://deck");
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(String(init.body)) : {};
    if (role !== "admin") return json({ error: "Solo el administrador puede usar el browser de la Instance." }, 403);
    const installed = container === "running" || container === "stopped";
    const route = `${method} ${url.pathname}`;
    if (route === "GET /api/browser") {
      return json({
        running: container === "running", unprotected: false, version: container === "running" ? "Chrome/130" : null, pages: [], uiPort: "3011",
        allowlist, config: { user: "agent", hasPassword }, sessions,
        install: { available: true, mode: "docker", image: installed, container, pulling: { active: false, line: "" } },
      });
    }
    if (route === "POST /api/browser/install") {
      if (!hasPassword) return json({ error: "Set a password before installing: it guards a browser holding live logins" }, 400);
      container = "running";
      return json({ ok: true });
    }
    if (route === "POST /api/browser/start" || route === "POST /api/browser/stop") {
      if (!installed) return json({ error: "Start failed (404)" }, 400);
      container = route.endsWith("start") ? "running" : "stopped";
      return json({ ok: true });
    }
    if (route === "DELETE /api/browser/install") {
      container = "absent";
      return json({ ok: true });
    }
    if (route === "PUT /api/browser/config") {
      if (body.password) hasPassword = true;
      return json({ user: body.user || "agent", hasPassword });
    }
    if (route === "GET /api/browser/suggest-password") return json({ password: "abcdef0123456789abcdef01" });
    if (route === "PUT /api/browser/allowlist") {
      allowlist = String(body.domains).split(/[\n,]/).map((d) => d.trim()).filter(Boolean).join("\n");
      return json({ allowlist });
    }
    const toggle = /^PUT \/api\/sessions\/([^/]+)\/browser$/.exec(route);
    if (toggle) {
      const at = sessions.findIndex((s) => s.id === toggle[1]);
      if (body.enabled && at < 0) sessions.push({ id: toggle[1], title: toggle[1], kind: "agent" });
      if (!body.enabled && at >= 0) sessions.splice(at, 1);
      return json({ enabled: Boolean(body.enabled) });
    }
    return json({ error: "Not found" }, 404);
  }) as typeof fetch;
}

function contract(name: string, open: (role: "admin" | "miembro") => BrowserApi) {
  describe(`BrowserApi: ${name}`, () => {
    it("a miembro is refused with a 403 on every call, reading included", async () => {
      const api = open("miembro");
      await expect(api.status()).rejects.toMatchObject({ status: 403 });
      await expect(api.install()).rejects.toMatchObject({ status: 403 });
      await expect(api.setSessionBrowser("s1", true)).rejects.toMatchObject({ status: 403 });
    });

    it("installing needs a password first; then it runs, stops and starts", async () => {
      const api = open("admin");
      expect((await api.status()).install.container).toBe("absent");
      await expect(api.install()).rejects.toMatchObject({ status: 400, message: expect.stringMatching(/password/) });
      await api.setConfig({ password: await api.suggestPassword() });
      await api.install();
      expect((await api.status()).running).toBe(true);
      await api.stop();
      expect((await api.status()).install.container).toBe("stopped");
      await api.start();
      expect((await api.status()).install.container).toBe("running");
      await api.remove();
      expect((await api.status()).install.container).toBe("absent");
    });

    it("start and stop with nothing installed are refused", async () => {
      const api = open("admin");
      await expect(api.start()).rejects.toMatchObject({ status: 400 });
    });

    it("the allowlist comes back one domain per line", async () => {
      const api = open("admin");
      expect(await api.setAllowlist(" a.example, *.b.example ")).toBe("a.example\n*.b.example");
      expect((await api.status()).allowlist).toBe("a.example\n*.b.example");
    });

    it("a Session's toggle is listed among the Sessions that may drive it, and off again", async () => {
      const api = open("admin");
      expect(await api.setSessionBrowser("s1", true)).toBe(true);
      expect((await api.status()).sessions.map((s) => s.id)).toEqual(["s1"]);
      expect(await api.setSessionBrowser("s1", false)).toBe(false);
      expect((await api.status()).sessions).toEqual([]);
    });
  });
}

contract("fetch adapter", (role) => fetchBrowserApi(deckBrowser(role)));
contract("fake", (role) => fakeBrowserApi({ forbidden: role !== "admin" }));
