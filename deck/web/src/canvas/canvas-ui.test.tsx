import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { canvasFixture } from "../ports/fakes/canvases";
import { CanvasBody } from "./canvas-body";
import { CanvasErrorBoundary, readCanvasUi } from "./canvas-ui";
import type { CanvasEffects } from "./catalog-registry";

afterEach(cleanup);

const spec = {
  root: "page",
  elements: {
    page: { type: "Stack", props: {}, children: ["filter", "table", "name", "go"] },
    filter: { type: "TextField", props: { label: "Filtro", value: { $bindState: "/q" } }, children: [] },
    table: {
      type: "Table",
      props: { columns: [{ key: "n", label: "Nombre" }], rows: { $state: "/rows" }, filter: { $state: "/q" } },
      children: [],
    },
    name: { type: "TextField", props: { label: "Nombre nuevo", value: { $bindState: "/name" } }, children: [] },
    go: { type: "Button", props: { label: "Preguntar" }, on: { press: { action: "askAgent", params: { message: "hola" } } }, children: [] },
  },
  state: { q: "", name: "", rows: [{ n: "Ana" }, { n: "Beto" }] },
};
const uiCanvas = (content: unknown) => canvasFixture({ id: "u", kind: "ui", content: typeof content === "string" ? content : JSON.stringify(content) });

function effects() {
  return { askAgent: vi.fn<CanvasEffects["askAgent"]>(async () => undefined) };
}

describe("readCanvasUi (controlador)", () => {
  it("un spec válido sale tal cual, con su estado", () => {
    expect(readCanvasUi(JSON.stringify(spec))).toMatchObject({ ok: true, spec: { root: "page", state: { q: "" } } });
  });
  it("un Canvas sin contenido todavía es una página en blanco, no un error", () => {
    expect(readCanvasUi("")).toEqual({ ok: false, kind: "empty", message: expect.any(String) });
  });
  it("JSON roto, spec inválido y componente fuera del catálogo son errores con mensaje", () => {
    expect(readCanvasUi("{no json")).toMatchObject({ ok: false, kind: "invalid" });
    expect(readCanvasUi(JSON.stringify({ root: "x" }))).toMatchObject({ ok: false, kind: "invalid" });
    const r = readCanvasUi(JSON.stringify({ root: "a", elements: { a: { type: "Iframe", props: {}, children: [] } } }));
    expect(r).toMatchObject({ ok: false, kind: "invalid" });
    expect(!r.ok && r.message).toMatch(/Iframe/);
  });
  it("lo que salió del catálogo (SourceCard, callTool, openDocument) ya no se pinta ni se ejecuta", () => {
    expect(readCanvasUi(JSON.stringify({ root: "a", elements: { a: { type: "SourceCard", props: { title: "x", excerpt: "y" }, children: [] } } }))).toMatchObject({ ok: false, kind: "invalid" });
    const button = (action: string) => ({ root: "a", elements: { a: { type: "Button", props: { label: "x" }, on: { press: { action, params: {} } }, children: [] } } });
    for (const action of ["callTool", "openDocument"]) expect(readCanvasUi(JSON.stringify(button(action)))).toMatchObject({ ok: false, kind: "invalid" });
  });
});

describe("CanvasBody ui (render con spec fija)", () => {
  it("pinta los componentes del spec con su estado", () => {
    render(<CanvasBody canvas={uiCanvas(spec)} effects={effects()} />);
    expect(screen.getByRole("table")).toBeTruthy();
    expect(screen.getByText("Ana")).toBeTruthy();
    expect(screen.getByText("Beto")).toBeTruthy();
  });

  it("filtrar la tabla y rellenar campos es local: no llama a ningún efecto", () => {
    const fx = effects();
    render(<CanvasBody canvas={uiCanvas(spec)} effects={fx} />);
    fireEvent.change(screen.getByLabelText("Filtro"), { target: { value: "an" } });
    expect(screen.queryByText("Beto")).toBeNull();
    expect(screen.getByText("Ana")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Nombre nuevo"), { target: { value: "Carla" } });
    expect((screen.getByLabelText("Nombre nuevo") as HTMLInputElement).value).toBe("Carla");
    expect(fx.askAgent).not.toHaveBeenCalled();
  });

  it("un botón con askAgent llama a su efecto con el mensaje", async () => {
    const fx = effects();
    render(<CanvasBody canvas={uiCanvas(spec)} effects={fx} />);
    fireEvent.click(screen.getByRole("button", { name: "Preguntar" }));
    await vi.waitFor(() => expect(fx.askAgent).toHaveBeenCalledWith("hola"));
  });

  it("un formulario: validateForm y askAgent mandan lo que la persona escribió", async () => {
    const fx = effects();
    const form = {
      root: "f",
      state: { form: { name: "" } },
      elements: {
        f: { type: "Stack", props: {}, children: ["name", "send"] },
        name: { type: "TextField", props: { label: "Tu nombre", value: { $bindState: "/form/name" } }, children: [] },
        send: {
          type: "Button", props: { label: "Enviar" }, children: [],
          on: { press: [{ action: "validateForm", params: {} }, { action: "askAgent", params: { message: { $template: "Me llamo ${/form/name}" } } }] },
        },
      },
    };
    render(<CanvasBody canvas={uiCanvas(form)} effects={fx} />);
    fireEvent.change(screen.getByLabelText("Tu nombre"), { target: { value: "Carla" } });
    fireEvent.click(screen.getByRole("button", { name: "Enviar" }));
    await vi.waitFor(() => expect(fx.askAgent).toHaveBeenCalledWith("Me llamo Carla"));
  });

  it("spec inválido: error acotado en el Canvas, con el mensaje, sin tirar el resto", () => {
    render(
      <div>
        <p>resto de la página</p>
        <CanvasBody canvas={uiCanvas({ root: "a", elements: { a: { type: "Iframe", props: {}, children: [] } } })} effects={effects()} />
      </div>,
    );
    expect(within(screen.getByRole("alert")).getByText(/Iframe/)).toBeTruthy();
    expect(screen.getByText("resto de la página")).toBeTruthy();
  });

  it("JSON ilegible: error acotado, no el texto del spec", () => {
    render(<CanvasBody canvas={uiCanvas("{no json")} effects={effects()} />);
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.queryByText("{no json")).toBeNull();
  });

  it("un fallo al pintar queda acotado por el error boundary del Canvas", () => {
    const caught: { message: string; stack: string }[] = [];
    const Boom = (): never => {
      throw new Error("boom");
    };
    render(
      <div>
        <p>resto</p>
        <CanvasErrorBoundary resetKey="r1" onError={(error, stack) => caught.push({ message: error.message, stack })}>
          <Boom />
        </CanvasErrorBoundary>
      </div>,
    );
    expect(screen.getByRole("alert").textContent).toMatch(/boom/);
    expect(screen.getByText("resto")).toBeTruthy();
    expect(caught).toHaveLength(1);
    expect(caught[0].message).toBe("boom");
    expect(caught[0].stack).toContain("Boom");
  });

  it("una acción setState explícita cambia el estado local y no llama a ningún efecto", async () => {
    const fx = effects();
    const withSetState = {
      ...spec,
      elements: {
        ...spec.elements,
        page: { ...spec.elements.page, children: [...spec.elements.page.children, "only"] },
        only: { type: "Button", props: { label: "Solo Ana" }, on: { press: { action: "setState", params: { statePath: "/q", value: "an" } } }, children: [] },
      },
    };
    render(<CanvasBody canvas={uiCanvas(withSetState)} effects={fx} />);
    expect(screen.getByText("Beto")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Solo Ana" }));
    await vi.waitFor(() => expect(screen.queryByText("Beto")).toBeNull());
    expect((screen.getByLabelText("Filtro") as HTMLInputElement).value).toBe("an");
    expect(fx.askAgent).not.toHaveBeenCalled();
  });
});
