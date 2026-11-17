import type { Canvas, CanvasActionResponse, CanvasStreamMessage } from "@deck/contract";
import { globalFetch, requestJson, type FetchLike } from "../http-errors";
import type { CanvasesApi } from "../canvases";
import { browserEventSource, type EventSourceLike } from "./fetch-sessions";

const root = (sessionId: string) => `/api/sessions/${encodeURIComponent(sessionId)}/canvases`;

/** The `fetch` adapter only knows HTTP: URL, status and JSON body (and the SSE stream). */
export function fetchCanvasesApi(fetchImpl: FetchLike = globalFetch, openStream: EventSourceLike = browserEventSource): CanvasesApi {
  return {
    list: (sessionId) => requestJson<Canvas[]>(fetchImpl, root(sessionId)),
    stream(sessionId, onMessage) {
      const source = openStream(`${root(sessionId)}/events`);
      source.onmessage = (e) => {
        try { onMessage(JSON.parse(e.data) as CanvasStreamMessage); } catch { /* a frame that is not a message */ }
      };
      return { close: () => source.close() };
    },
    async act(sessionId, canvasId, action) {
      await requestJson<CanvasActionResponse>(fetchImpl, `${root(sessionId)}/${encodeURIComponent(canvasId)}/actions`, { method: "POST", body: JSON.stringify(action) });
      return { kind: "asked" };
    },
  };
}
