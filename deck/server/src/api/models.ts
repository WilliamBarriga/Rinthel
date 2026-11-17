import express, { type Response as Reply, type Router } from "express";
import { accessTokenOf } from "../identity.js";
import type { DaemonClient } from "../daemon-client.js";
import type { ModelRouting } from "../model-routing/model-routing.js";
import { adminOnly } from "./admin-only.js";

/** The daemon's 409 codes of a switch, and what the admin reads for each. */
const REFUSED: Readonly<Record<string, string>> = {
  turns_in_flight: "Hay turnos en curso: espera a que terminen para cambiar el Local model.",
  lifecycle_busy: "El daemon está ocupado con otra operación (arranque, parada, recarga o instalación); inténtalo en un momento.",
};

/**
 * The Local model of the Instance (ADR 0008): one for every Session, only the admin changes it.
 *
 * - `GET /models/llm` (any user): the model every Session talks to now and its context window, for
 *   the composer.
 * - `GET /models` (admin): the daemon's catalog, as the daemon answers it.
 * - `POST /models/activate` (admin): refused here with `409 turns_in_flight` while any Session of this
 *   Deck is generating; otherwise the daemon switches (kill, spawn, ready, rollback) under its own lock
 *   and may refuse with its own 409. Sessions find out on their next call (`wrong_model`).
 */
export function modelsRouter(deps: { daemon: DaemonClient; routing: ModelRouting; generating: () => boolean }): Router {
  const { daemon, routing } = deps;
  const router = express.Router();
  const admin = adminOnly("el cambio de Local model");

  router.get("/models/llm", async (_req, res) => {
    try {
      const route = await routing.read("llm");
      res.json({ model: route?.model ?? null, context_window: route?.contextWindow ?? null });
    } catch (e) {
      res.status(502).json({ error: (e as Error).message });
    }
  });

  router.get("/models", admin, async (req, res) => {
    await relay(res, () => daemon.withPanelToken(accessTokenOf(req) ?? "").fetch("/models"));
  });

  router.post("/models/activate", admin, async (req, res) => {
    const id = req.body?.id;
    if (typeof id !== "string" || !id) return res.status(400).json({ error: "id required" });
    if (deps.generating()) return res.status(409).json({ error: REFUSED.turns_in_flight, code: "turns_in_flight" });
    await relay(res, () => daemon.withPanelToken(accessTokenOf(req) ?? "").fetch("/models/activate", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ id }),
    }));
  });

  return router;
}

/** The daemon's answer as the browser gets it: a success as is, a refusal as `{ error, code }`, a daemon that does not answer a 502. */
async function relay(res: Reply, call: () => Promise<Response>): Promise<void> {
  let upstream: Response;
  try {
    upstream = await call();
  } catch (e) {
    res.status(502).json({ error: `El daemon no responde: ${(e as Error).message}` });
    return;
  }
  const body = await upstream.json().catch(() => ({}));
  if (upstream.ok) {
    res.status(upstream.status).json(body);
    return;
  }
  const detail = typeof body?.detail === "string" ? body.detail : JSON.stringify(body?.detail ?? body);
  const code = detail.split(":")[0];
  res.status(upstream.status).json({ error: REFUSED[code] ?? detail, code });
}
