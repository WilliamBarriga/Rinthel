/**
 * Canvases: what `/api/sessions/:id/canvases` says to the front. Only the Agente writes; the
 * person reads (the front has no route that writes content).
 */

/** `markdown` es texto; `ui` es una estructura de componentes del catálogo (`@deck/canvas-catalog`). */
export type CanvasKind = "markdown" | "ui";

/** One Canvas of a Sesión. For a `ui` Canvas, `content` is the JSON text of its spec. */
export interface Canvas {
  id: string;
  session_id: string;
  kind: CanvasKind;
  title: string;
  content: string;
  /** Grows with every write; a person reading it never sends it back. */
  revision: number;
  status: string;
  /** The tool call that is writing it right now, or `null` when nobody is. */
  active_call: string | null;
  updated_at: string;
  /** In the database (`true`) or only in the server's memory (`false`). */
  persisted: boolean;
}

/**
 * One SSE message of `GET /api/sessions/:id/canvases/events` (no `seq`: the stream has no
 * cursor, a reconnect starts with a `snapshot`). `focus` asks the person to look at that Canvas.
 */
export type CanvasStreamMessage =
  | { type: "snapshot"; canvases: Canvas[] }
  | { type: "create" | "update" | "focus"; canvas: Canvas }
  | { type: "delete"; id: string };

/** The one action of a `ui` Canvas that leaves the browser (`POST /api/sessions/:id/canvases/:canvasId/actions`). */
export type CanvasAction = { action: "askAgent"; params: { message: string } };

/** The body the server answers an action with: `{ ok: true }`, the message waits in the Sesión and no turn starts. */
export type CanvasActionResponse = { ok: true };

/** What the port hands the front once the action went through. */
export type CanvasActionResult = { kind: "asked" };
