import { describe, expect, it } from "vitest";
import type { Canvas, CanvasAction, CanvasStreamMessage } from "@deck/contract";
import { fetchCanvasesApi } from "./adapters/fetch-canvases";
import type { CanvasesApi } from "./canvases";
import { canvasFixture, fakeCanvasesApi } from "./fakes/canvases";
import { PortError } from "./http-errors";

const MINE = [canvasFixture({ id: "b", title: "Second", kind: "ui", content: '{"root":"r"}' }), canvasFixture({ id: "a", title: "First", revision: 3, active_call: "call-1" })];
const OTHER = canvasFixture({ id: "z", session_id: "s2" });

/** A tiny stand-in for `/api/sessions/:id/canvases`, with its own state (not the fake). */
function canvasesServer(canvases: Canvas[]) {
  return async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const act = /^\/api\/sessions\/([^/]+)\/canvases\/([^/]+)\/actions$/.exec(String(input));
    if (act && init?.method === "POST") {
      const [session, canvas] = [decodeURIComponent(act[1]), decodeURIComponent(act[2])];
      if (!canvases.some((c) => c.session_id === session && c.id === canvas)) return Response.json({ error: "Canvas not found in this session" }, { status: 404 });
      const body = JSON.parse(String(init.body)) as CanvasAction;
      if (body.action !== "askAgent") return Response.json({ error: "Unknown action" }, { status: 400 });
      return body.params.message.trim() ? Response.json({ ok: true }) : Response.json({ error: "empty" }, { status: 400 });
    }
    const m = /^\/api\/sessions\/([^/]+)\/canvases$/.exec(String(input));
    if (!m || (init?.method ?? "GET") !== "GET") return Response.json({ error: "No such route" }, { status: 404 });
    const session = decodeURIComponent(m[1]);
    if (!canvases.some((c) => c.session_id === session)) return Response.json({ error: "Session not found" }, { status: 404 });
    return Response.json(canvases.filter((c) => c.session_id === session));
  };
}

/** Same suite for every adapter of the port; it only uses the interface. */
function canvasesApiContract(name: string, make: (canvases: Canvas[]) => CanvasesApi) {
  describe(`CanvasesApi (${name})`, () => {
    it("lista los Canvases de la Sesión con su kind, revision y active_call, y no los de otra", async () => {
      const list = await make([...MINE, OTHER]).list("s1");
      expect(list.map((c) => c.id)).toEqual(["b", "a"]);
      expect(list.map((c) => c.kind)).toEqual(["ui", "markdown"]);
      expect(list[1]).toMatchObject({ revision: 3, active_call: "call-1" });
    });

    it("una Sesión que no existe rechaza con un 404", async () => {
      await expect(make(MINE).list("nope")).rejects.toMatchObject({ kind: "http", status: 404 });
    });

    it("askAgent deja el mensaje en la Sesión", async () => {
      expect(await make([...MINE]).act("s1", "a", { action: "askAgent", params: { message: "explica esto" } })).toEqual({ kind: "asked" });
    });

    it("un Canvas que no es de la Sesión rechaza con un 404", async () => {
      await expect(make([...MINE]).act("s1", "nope", { action: "askAgent", params: { message: "hola" } })).rejects.toMatchObject({ kind: "http", status: 404 });
    });

    it("una acción inválida rechaza con un 400", async () => {
      await expect(make([...MINE]).act("s1", "a", { action: "askAgent", params: { message: "  " } })).rejects.toMatchObject({ kind: "http", status: 400 });
    });
  });
}

canvasesApiContract("fake", (canvases) => fakeCanvasesApi({ canvases }));
canvasesApiContract("fetch", (canvases) => fetchCanvasesApi(canvasesServer(canvases)));

describe("fetchCanvasesApi", () => {
  it("pide la lista con GET a la ruta de la Sesión", async () => {
    const calls: { url: string; method?: string }[] = [];
    await fetchCanvasesApi(async (input, init) => {
      calls.push({ url: String(input), method: init?.method });
      return Response.json([]);
    }).list("s1");
    expect(calls).toEqual([{ url: "/api/sessions/s1/canvases", method: undefined }]);
  });

  it("un 401 y un 502 rechazan con su tipo", async () => {
    const down = fetchCanvasesApi(async () => Response.json({ error: "daemon caído" }, { status: 502 }));
    await expect(down.list("s1")).rejects.toMatchObject({ kind: "unavailable" });
    const out = fetchCanvasesApi(async () => new Response("{}", { status: 401 }));
    await expect(out.list("s1")).rejects.toBeInstanceOf(PortError);
    await expect(out.list("s1")).rejects.toMatchObject({ kind: "unauthorized" });
  });

  it("hace POST a la ruta de acciones del Canvas con la acción como cuerpo", async () => {
    const calls: { url: string; method?: string; body?: unknown }[] = [];
    await fetchCanvasesApi(async (input, init) => {
      calls.push({ url: String(input), method: init?.method, body: JSON.parse(String(init?.body)) });
      return Response.json({ ok: true });
    }).act("s 1", "c/1", { action: "askAgent", params: { message: "hola" } });
    expect(calls).toEqual([{ url: "/api/sessions/s%201/canvases/c%2F1/actions", method: "POST", body: { action: "askAgent", params: { message: "hola" } } }]);
  });

  it("un 403 (la persona no es dueña de la Sesión) es un error con el motivo del servidor", async () => {
    const api = fetchCanvasesApi(async () => Response.json({ error: "Forbidden" }, { status: 403 }));
    await expect(api.act("s1", "a", { action: "askAgent", params: { message: "hola" } })).rejects.toMatchObject({ kind: "http", status: 403, message: "Forbidden" });
  });

  it("el stream se abre en la ruta de eventos de la Sesión y entrega cada mensaje; cerrarlo cierra la conexión", () => {
    const opened: string[] = [];
    let closed = false;
    const source = { onmessage: null as ((e: MessageEvent) => void) | null, addEventListener() {}, close: () => { closed = true; } };
    const got: CanvasStreamMessage[] = [];
    const subscription = fetchCanvasesApi(async () => Response.json([]), (url) => { opened.push(url); return source; }).stream("s 1", (m) => got.push(m));
    expect(opened).toEqual(["/api/sessions/s%201/canvases/events"]);
    source.onmessage?.({ data: JSON.stringify({ type: "snapshot", canvases: [] }) } as MessageEvent);
    source.onmessage?.({ data: "not json" } as MessageEvent);
    expect(got).toEqual([{ type: "snapshot", canvases: [] }]);
    subscription.close();
    expect(closed).toBe(true);
  });
});

describe("fakeCanvasesApi", () => {
  it("registra las acciones y los mensajes dejados", async () => {
    const api = fakeCanvasesApi({ canvases: MINE });
    await api.act("s1", "a", { action: "askAgent", params: { message: " explica esto " } });
    expect(api.notes).toEqual([{ sessionId: "s1", text: "explica esto" }]);
    expect(api.actions.map((a) => a.action.action)).toEqual(["askAgent"]);
  });

  it("write guarda lo que escribe el Agente (el más nuevo primero), lo envía al stream y failNext falla solo la siguiente lectura", async () => {
    const api = fakeCanvasesApi({ canvases: MINE });
    const got: CanvasStreamMessage[] = [];
    api.stream("s1", (m) => got.push(m));
    api.write(canvasFixture({ id: "c", title: "Third" }), "create");
    expect(got.map((m) => m.type)).toEqual(["snapshot", "create"]);
    api.write(canvasFixture({ id: "a", title: "First v2", revision: 4 }));
    expect((await api.list("s1")).map((c) => [c.id, c.revision])).toEqual([["a", 4], ["c", 1], ["b", 1]]);
    api.failNext("list", new PortError("network", 0, "sin red"));
    await expect(api.list("s1")).rejects.toMatchObject({ kind: "network" });
    await expect(api.list("s1")).resolves.toHaveLength(3);
    expect(api.listCalls).toBe(3);
  });
});
