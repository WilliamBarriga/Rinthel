import { createElement, type ComponentType } from "react";
import { CanvasErrorBoundary } from "./canvas-error-boundary";
import { defineRegistry } from "@json-render/react";
import { canvasCatalog } from "@deck/canvas-catalog";
import { Button, Card, CheckboxField, Heading, Metric, SelectField, Stack, Table, Text, TextField } from "./catalog-components";

/** Catch inside json-render, whose own element boundary otherwise hides a failed view.
 * CanvasUi remounts the registry tree on id:revision, clearing these failures too. */
function bounded<P extends object>(View: ComponentType<P>) {
  return function CanvasElement(props: P) {
    return createElement(CanvasErrorBoundary, { resetKey: "element", children: createElement(View, props) });
  };
}
const views = {
  Heading: bounded(Heading), Text: bounded(Text), Table: bounded(Table), Metric: bounded(Metric),
  Card: bounded(Card), Stack: bounded(Stack), Button: bounded(Button),
  TextField: bounded(TextField), SelectField: bounded(SelectField), CheckboxField: bounded(CheckboxField),
};

/** What the Canvas needs from the app to act on a catalog action. */
export interface CanvasEffects {
  /** «Ask the agent about this»: leaves a message in the Session. It starts no turn. */
  askAgent: (message: string) => Promise<void>;
}

/**
 * The front's registry for the Canvas catalog: component name → view, plus the
 * the one action with effect (`askAgent`, through the server). `JSONUIProvider` takes `registry` and `handlers`.
 * `setState` and the other local actions are built into json-render.
 */
export function canvasRegistry(effects: CanvasEffects) {
  return defineRegistry(canvasCatalog, {
    components: views,
    actions: {
      askAgent: async (params) => {
        // The browser resolves a form field or a template into text before the handler runs.
        if (params && typeof params.message === "string") await effects.askAgent(params.message);
      },
    },
  });
}
