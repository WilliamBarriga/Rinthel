import type { Canvas, CanvasAction, CanvasActionResult, CanvasStreamMessage } from "@deck/contract";
import type { EventSubscription } from "./sessions";

/**
 * Port: the Canvases of a Sesión (`/api/sessions/:id/canvases` of Node), read only: the Agente is
 * the only one who writes them, so there is no create, edit or delete here. Failures reject with a
 * `PortError` (see `http-errors.ts`).
 *
 * `list` is the current state, newest first. What changes while the Agente writes travels over
 * `stream` as `CanvasStreamMessage`s; every (re)connection starts with a `snapshot`, and the
 * stream reconnects on its own. The `.md` that a person downloads is built from the Canvas the
 * person is looking at, which is always at least as new as anything the server could send back.
 *
 * `act` is the only thing a person does to a Canvas that leaves the browser (the local actions,
 * filters and fields, never come here): «preguntar al agente» leaves a message in the Sesión and
 * starts no turn. A Canvas the Sesión does not have is `404` and an invalid action `400`.
 */
export interface CanvasesApi {
  list(sessionId: string): Promise<Canvas[]>;
  stream(sessionId: string, onMessage: (message: CanvasStreamMessage) => void): EventSubscription;
  act(sessionId: string, canvasId: string, action: CanvasAction): Promise<CanvasActionResult>;
}
