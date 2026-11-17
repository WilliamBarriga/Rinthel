import type { ReactNode } from "react";
import { Streamdown } from "streamdown";
import type { Canvas } from "@deck/contract";
import { CanvasUi } from "./canvas-ui";
import type { CanvasEffects } from "./catalog-registry";

/**
 * What the front can do for a Canvas beyond painting it. The default does nothing: whoever shows
 * the Canvas wires what it has (`CanvasPanel` wires `askAgent` over `canvasesApi.act`, in
 * `useCanvasActions`). Local actions (filters, fields) never come here.
 */
const NO_EFFECTS: CanvasEffects = { askAgent: async () => {} };

type Render = (canvas: Canvas, effects: CanvasEffects) => ReactNode;

/**
 * How each `kind` of Canvas is shown: the extension point of the panel. A new kind is a new
 * entry here (the compiler asks for it); the panel and its controller do not change.
 * `markdown` is read only; `ui` is its spec painted with the json-render catalog (`CanvasUi`).
 */
const RENDERERS: Record<Canvas["kind"], Render> = {
  markdown: (canvas) => (canvas.content ? <Streamdown>{canvas.content}</Streamdown> : <p className="canvas-empty">A blank page. Ask the agent to write here.</p>),
  ui: (canvas, effects) => <CanvasUi id={canvas.id} revision={canvas.revision} content={canvas.content} effects={effects} />,
};

/** The body of a Canvas by its `kind`; a kind this front does not know is a notice, not a crash. */
export function CanvasBody({ canvas, effects = NO_EFFECTS }: { canvas: Canvas; effects?: CanvasEffects }) {
  const render = RENDERERS[canvas.kind] as Render | undefined;
  return <>{render ? render(canvas, effects) : <p role="alert" className="canvas-error">Unknown canvas kind “{String(canvas.kind)}”.</p>}</>;
}
