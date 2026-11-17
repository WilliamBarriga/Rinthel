import { describe, expect, it } from "vitest";
import { messageOf, PortError, requestJson, toViewError } from "./http-errors";

const never = (): never => {
  throw new Error("no debía llamarse");
};

describe("requestJson", () => {
  it("devuelve el JSON de una respuesta ok", async () => {
    const out = await requestJson<{ a: number }>(async () => Response.json({ a: 1 }), "/api/x");
    expect(out).toEqual({ a: 1 });
  });

  it("manda JSON con el método y el cuerpo pedidos", async () => {
    let seen: { url: string; init?: RequestInit } | null = null;
    await requestJson(
      async (url, init) => {
        seen = { url: String(url), init };
        return Response.json({});
      },
      "/api/x",
      { method: "POST", body: JSON.stringify({ k: 1 }) },
    );
    expect(seen!.url).toBe("/api/x");
    expect(seen!.init?.method).toBe("POST");
    expect(new Headers(seen!.init?.headers).get("Content-Type")).toBe("application/json");
  });

  it("un 401 es 'unauthorized' y conserva el mensaje del cuerpo", async () => {
    const err = await requestJson(async () => Response.json({ error: "bad creds" }, { status: 401 }), "/api/x").catch((e) => e);
    expect(err).toBeInstanceOf(PortError);
    expect(err).toMatchObject({ kind: "unauthorized", status: 401, message: "bad creds" });
  });

  it("un 502 es 'unavailable' (daemon caído)", async () => {
    const err = await requestJson(async () => Response.json({ error: "daemon caído" }, { status: 502 }), "/api/x").catch((e) => e);
    expect(err).toMatchObject({ kind: "unavailable", status: 502, message: "daemon caído" });
  });

  it("los demás status pasan con su cuerpo y, sin cuerpo JSON, con 'HTTP <status>'", async () => {
    const withBody = await requestJson(async () => Response.json({ error: "nope", extra: 1 }, { status: 409 }), "/api/x").catch((e) => e);
    expect(withBody).toMatchObject({ kind: "http", status: 409, message: "nope", body: { error: "nope", extra: 1 } });
    const bare = await requestJson(async () => new Response("boom", { status: 500 }), "/api/x").catch((e) => e);
    expect(bare).toMatchObject({ kind: "http", status: 500, message: "HTTP 500" });
  });

  it("un fallo de red es 'network'", async () => {
    const err = await requestJson(async () => never(), "/api/x").catch((e) => e);
    expect(err).toMatchObject({ kind: "network", status: 0 });
  });

  it("el cuerpo de error del daemon (`detail` de FastAPI) llega como mensaje, para mostrarlo tal cual", async () => {
    const err = await requestJson(async () => Response.json({ detail: "a pattern is required" }, { status: 422 }), "/api/x").catch((e) => e);
    expect(err).toMatchObject({ kind: "http", status: 422, message: "a pattern is required" });
  });
});

describe("toViewError", () => {
  it("un PortError conserva su tipo y su mensaje", () => {
    expect(toViewError(new PortError("unauthorized", 401, "sesión caducada"))).toEqual({ kind: "unauthorized", message: "sesión caducada" });
  });

  it("un Error cualquiera es 'unknown' con su mensaje", () => {
    expect(toViewError(new Error("boom"))).toEqual({ kind: "unknown", message: "boom" });
  });

  it("algo que no es un Error se muestra como texto", () => {
    expect(toViewError("roto")).toEqual({ kind: "unknown", message: "roto" });
  });
});

describe("messageOf", () => {
  it("toma el mensaje de un Error y el texto de lo demás", () => {
    expect(messageOf(new Error("x"))).toBe("x");
    expect(messageOf(42)).toBe("42");
  });
});

it("el mensaje legible de un conflicto estructurado del daemon llega al usuario", async () => {
  const fetchImpl = async () => Response.json({ detail: { code: "generation_building", message: "La Generación de índice está en construcción." } }, { status: 409 });
  await expect(requestJson(fetchImpl, "/documents", { method: "GET" })).rejects.toMatchObject({
    status: 409, message: "La Generación de índice está en construcción.",
  });
});
