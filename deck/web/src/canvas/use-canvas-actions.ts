import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useCanvasesApi } from "../ports/context";
import { messageOf } from "../ports/http-errors";
import type { CanvasEffects } from "./catalog-registry";

/** What the person is told about the last action that left the browser. */
export type CanvasActionNotice = { tone: "ok" | "error"; text: string };

/**
 * Controller of the one action of a `ui` Canvas that goes through the server, `askAgent`: it leaves
 * a message in the Sesión and starts no turn (the Agente reads it on its next one). Local actions
 * (filters, fields, `setState`) never reach this hook, so an ordinary click asks the server for
 * nothing. The outcome is a `notice` shown under the Canvas, outside its scroll, because
 * json-render hands a handler no element to pin it to. A failure becomes an `error` notice; nothing
 * throws into a view, and an answer that arrives after the person moved to another Canvas is dropped.
 */
export function useCanvasActions(sessionId: string, canvasId: string | undefined) {
  const canvasesApi = useCanvasesApi();
  const [notice, setNotice] = useState<CanvasActionNotice | null>(null);
  const current = useRef(canvasId);
  useEffect(() => {
    current.current = canvasId;
    setNotice(null);
  }, [sessionId, canvasId]);

  const askAgent = useCallback(
    async (message: string) => {
      if (!canvasId) return;
      const asked = canvasId;
      const show = (n: CanvasActionNotice): void => {
        if (current.current === asked) setNotice(n);
      };
      try {
        await canvasesApi.act(sessionId, asked, { action: "askAgent", params: { message } });
        show({ tone: "ok", text: "Enviado al Agente. Lo leerá en su próximo turno." });
      } catch (e) {
        show({ tone: "error", text: messageOf(e) });
      }
    },
    [canvasesApi, sessionId, canvasId],
  );

  const effects = useMemo<CanvasEffects>(() => ({ askAgent }), [askAgent]);
  return { effects, notice, dismiss: useCallback(() => setNotice(null), []) };
}
