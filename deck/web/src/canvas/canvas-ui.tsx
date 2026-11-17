import { useMemo } from "react";
import { CanvasErrorBoundary } from "./canvas-error-boundary";
export { CanvasErrorBoundary } from "./canvas-error-boundary";
import { JSONUIProvider, Renderer, type SetState, type Spec } from "@json-render/react";
import { validateCanvasSpec, type CanvasSpec } from "@deck/canvas-catalog";
import { canvasRegistry, type CanvasEffects } from "./catalog-registry";

/** What a `ui` Canvas's text says: a spec to paint, or why there is nothing to paint. */
export type CanvasUiRead =
  | { ok: true; spec: CanvasSpec }
  | { ok: false; kind: "empty" | "invalid"; message: string };

/**
 * The controller of a `ui` Canvas: its `content` is the JSON text of a spec, which the server
 * already validated on write. The front checks it again with the same catalog, because a stored
 * Canvas can outlive the catalog it was written against. Pure: no I/O, no throw.
 */
export function readCanvasUi(content: string): CanvasUiRead {
  if (!content.trim()) return { ok: false, kind: "empty", message: "A blank interface. Ask the agent to build it." };
  let json: unknown;
  try {
    json = JSON.parse(content);
  } catch {
    return { ok: false, kind: "invalid", message: "This interface canvas is not valid JSON." };
  }
  const checked = validateCanvasSpec(json);
  if (checked.ok) return checked;
  const detail = checked.issues.map((issue) => issue.message).join("; ");
  return { ok: false, kind: "invalid", message: `This interface canvas is invalid: ${detail}` };
}

/**
 * The registry's handlers refuse to run without a `SetState`. Ours is an effect (`askAgent`)
 * that never writes state; `setState` and the local actions are json-render's own.
 */
const keepsNoState: SetState = () => {};

/** The validated spec in the shape the renderer types: `props` is optional in a spec, required there. */
function renderable(spec: CanvasSpec): Spec {
  const elements: Spec["elements"] = {};
  for (const [key, element] of Object.entries(spec.elements)) elements[key] = { ...element, type: String(element.type), props: element.props ?? {} };
  return { root: spec.root, elements, state: spec.state };
}

function CanvasUiView({ spec, effects }: { spec: CanvasSpec; effects: CanvasEffects }) {
  const { registry, handlers } = useMemo(() => canvasRegistry(effects), [effects]);
  const initial = spec.state ?? {};
  const tree = useMemo(() => renderable(spec), [spec]);
  // `setState` and the other local actions live inside json-render: filters and fields never reach `effects`.
  return (
    <JSONUIProvider registry={registry} initialState={initial} handlers={handlers(() => keepsNoState, () => initial)}>
      <Renderer spec={tree} registry={registry} />
    </JSONUIProvider>
  );
}

/** What the app does with a failed Canvas view unless told otherwise: leave it in the browser console. */
function logCanvasError(error: Error, componentStack: string) {
  console.error("Canvas view failed", error, componentStack);
}

/** A `ui` Canvas: its spec painted with the catalog, or a bounded notice; never a crash of the page. */
export function CanvasUi({ id, revision, content, effects, onError = logCanvasError }: { id: string; revision: number; content: string; effects: CanvasEffects; onError?: (error: Error, componentStack: string) => void }) {
  const read = useMemo(() => readCanvasUi(content), [content]);
  if (!read.ok) {
    return read.kind === "empty" ? <p className="canvas-empty">{read.message}</p> : <p role="alert" className="canvas-error">{read.message}</p>;
  }
  return (
    <CanvasErrorBoundary resetKey={`${id}:${revision}`} onError={onError}>
      {/* A new revision is a new spec with its own state: remount rather than merge into the old one. */}
      <CanvasUiView key={`${id}:${revision}`} spec={read.spec} effects={effects} />
    </CanvasErrorBoundary>
  );
}
