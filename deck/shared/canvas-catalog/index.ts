/**
 * Catálogo del Canvas `ui`: lo único que el modelo puede pedir que se pinte.
 *
 * Es el contrato entre tres lados y vive en un solo módulo: el servidor lo usa
 * para validar `canvas_write` (y para enseñárselo al modelo), el front lo usa
 * para tipar su registro de componentes. Zod solo aparece aquí; el registro de
 * componentes (React) es del front.
 *
 * Interface: `validateCanvasSpec` (el único camino de entrada), `COMPONENT_NAMES`,
 * `ACTION_NAMES`, `canvasCatalogPrompt`, `canvasCatalog` y los tipos de props.
 * Cerrado a propósito: sin `Html`, sin `Link` libre, sin gráficos. Añadir un
 * componente es añadirlo a `components` y a su registro del front, nada más.
 */
import { defineCatalog, validateSpec } from '@json-render/core';
import { schema } from '@json-render/react/schema';
import { z } from 'zod';

/** Expresiones de json-render que pueden ocupar el lugar de un valor literal. */
const expression = z.union([
  z.strictObject({ $state: z.string() }),
  z.strictObject({ $item: z.string() }),
  z.strictObject({ $index: z.literal(true) }),
  z.strictObject({ $bindState: z.string() }),
  z.strictObject({ $bindItem: z.string() }),
  z.strictObject({ $template: z.string() }),
  z.looseObject({ $cond: z.unknown(), $then: z.unknown(), $else: z.unknown() }),
]);

/** Un objeto de props en el que cada campo acepta su literal o una expresión. */
function props<S extends z.ZodRawShape>(shape: S) {
  const wrapped = Object.fromEntries(
    Object.entries(shape).map(([key, field]) => [key, z.union([expression, field as z.ZodType])]),
  );
  return z.strictObject(wrapped) as unknown as z.ZodObject<S, z.core.$strict>;
}

const cell = z.union([z.string(), z.number(), z.boolean(), z.null()]);

export const components = {
  Heading: {
    props: props({ text: z.string(), level: z.union([z.literal(1), z.literal(2), z.literal(3)]).nullish() }),
    description: 'Título de sección. level 1 a 3 (por defecto 2).',
  },
  Text: {
    props: props({ content: z.string() }),
    description: 'Párrafo en Markdown (negrita, listas, código). Los enlaces no son clicables.',
  },
  Table: {
    props: props({
      columns: z.array(z.strictObject({ key: z.string(), label: z.string() })),
      rows: z.array(z.record(z.string(), cell)),
      filter: z.string().nullish(),
    }),
    description:
      'Tabla. columns define clave y encabezado; rows son objetos por clave, normalmente {"$state":"/ruta"} para que los datos vivan en el estado. filter: texto que oculta las filas que no lo contienen, normalmente {"$bindState":"/ruta"} ligado a un TextField.',
  },
  Metric: {
    props: props({ label: z.string(), value: z.union([z.string(), z.number()]), detail: z.string().nullish() }),
    description: 'Una cifra destacada con su etiqueta y un detalle opcional.',
  },
  Card: {
    props: props({ title: z.string().nullish() }),
    description: 'Contenedor con borde y título opcional; agrupa a sus hijos.',
    slots: ['default'] as string[],
  },
  Stack: {
    props: props({
      direction: z.enum(['vertical', 'horizontal']).nullish(),
      gap: z.enum(['sm', 'md', 'lg']).nullish(),
    }),
    description: 'Apila a sus hijos en vertical (por defecto) u horizontal. Con repeat pinta una vez por elemento del estado.',
    slots: ['default'] as string[],
  },
  Button: {
    props: props({ label: z.string(), variant: z.enum(['primary', 'secondary']).nullish() }),
    description:
      'Botón. Emite el evento "press"; úsalo con on.press y una acción (setState, askAgent). Un clic no inicia un turno del agente.',
  },
  TextField: {
    props: props({
      label: z.string(),
      value: z.string().nullish(),
      placeholder: z.string().nullish(),
      inputType: z.enum(['text', 'number', 'date']).nullish(),
    }),
    description: 'Campo de texto. value va ligado al estado con {"$bindState":"/ruta"}.',
  },
  SelectField: {
    props: props({
      label: z.string(),
      value: z.string().nullish(),
      options: z.array(z.strictObject({ value: z.string(), label: z.string() })),
    }),
    description: 'Lista desplegable. value va ligado al estado con {"$bindState":"/ruta"}.',
  },
  CheckboxField: {
    props: props({ label: z.string(), value: z.boolean().nullish() }),
    description: 'Casilla. value va ligado al estado con {"$bindState":"/ruta"}.',
  },
} as const;

/** Acciones que el catálogo permite. Las de estado son locales (sin red). */
const askAgentText = z.string().min(1).max(4000);
/** What reaches the server: the message already resolved by the browser, as plain text. */
const serverParams = { askAgent: z.strictObject({ message: askAgentText }) } as const;
export const actions = {
  askAgent: {
    // In a spec the message may be an expression (a form field, a template); the browser resolves it before it leaves.
    params: z.strictObject({ message: z.union([expression, askAgentText]) }),
    description:
      'Deja un mensaje en la Sesión para el agente («preguntar al agente sobre esto»). El clic no inicia un turno: el agente lo lee en el siguiente. Params: { message: string } (puede ser una expresión, p. ej. {"$template":"...${/form/name}"}).',
  },
} as const;

/**
 * La única tabla de acciones: dónde corre cada una. `local` es de json-render (sin red) y `server` viaja al portal. `ACTION_NAMES`, `SERVER_ACTION_NAMES` y
 * los tipos salen de aquí; una acción nueva del catálogo no compila hasta tener fila.
 */
export type ActionRun = 'local' | 'server';
export const ACTION_RUNS = {
  setState: 'local',
  pushState: 'local',
  removeState: 'local',
  validateForm: 'local',
  askAgent: 'server',
} as const satisfies Record<keyof typeof actions | 'setState' | 'pushState' | 'removeState' | 'validateForm', ActionRun>;

export const canvasCatalog = defineCatalog(schema, { components, actions });

export type ComponentName = keyof typeof components;
export type ActionName = keyof typeof ACTION_RUNS;
export type ComponentProps<N extends ComponentName> = z.infer<(typeof components)[N]['props']>;

export const COMPONENT_NAMES = Object.keys(components) as ComponentName[];
export const ACTION_NAMES = Object.keys(ACTION_RUNS) as ActionName[];

/** Acciones que el servidor ejecuta (el resto del catálogo corre en el navegador). */
export type ServerActionName = { [N in ActionName]: (typeof ACTION_RUNS)[N] extends 'server' ? N : never }[ActionName] & keyof typeof actions;
export const SERVER_ACTION_NAMES = ACTION_NAMES.filter((name): name is ServerActionName => ACTION_RUNS[name] === 'server');
export type ServerAction = { [N in ServerActionName]: { action: N; params: z.infer<(typeof serverParams)[N]> } }[ServerActionName];

/**
 * Valida la acción que el navegador manda al servidor con las mismas props que
 * el catálogo le enseña al modelo. Solo `askAgent` viaja: las
 * locales no tocan la red.
 */
export function canvasActionParams(name: unknown, params: unknown): ({ ok: true } & ServerAction) | { ok: false; message: string } {
  if (typeof name !== 'string' || !(SERVER_ACTION_NAMES as readonly string[]).includes(name)) {
    return { ok: false, message: `La acción "${String(name)}" no la ejecuta el servidor (${SERVER_ACTION_NAMES.join(', ')}).` };
  }
  const parsed = serverParams[name as ServerActionName].safeParse(params ?? {});
  if (!parsed.success) return { ok: false, message: `Acción ${name}: ${parsed.error.issues[0].message}` };
  return { ok: true, action: name, params: parsed.data } as { ok: true } & ServerAction;
}

export type CanvasSpecIssueCode = 'invalid_spec' | 'unknown_component' | 'invalid_props' | 'unknown_action' | 'structure';
export interface CanvasSpecIssue {
  code: CanvasSpecIssueCode;
  /** Clave del elemento (no existe en los errores de la forma general). */
  element?: string;
  /** Prop o acción dentro del elemento. */
  path?: string;
  message: string;
}
export type CanvasSpec = { root: string; elements: Record<string, Record<string, any>>; state?: Record<string, unknown> };
export type CanvasSpecResult = { ok: true; spec: CanvasSpec } | { ok: false; issues: CanvasSpecIssue[] };

const isRecord = (v: unknown): v is Record<string, any> => typeof v === 'object' && v !== null && !Array.isArray(v);

/** Todos los bindings de acción de un elemento (`on` y `watch`), en una lista plana. */
function bindings(element: Record<string, any>): { name: unknown; params: unknown }[] {
  const out: { name: unknown; params: unknown }[] = [];
  for (const group of [element.on, element.watch]) {
    if (!isRecord(group)) continue;
    for (const value of Object.values(group)) {
      for (const b of Array.isArray(value) ? value : [value]) if (isRecord(b)) out.push({ name: b.action, params: b.params });
    }
  }
  return out;
}

/**
 * Valida un spec de Canvas `ui` contra el catálogo: forma, componentes, props,
 * acciones y referencias entre elementos. Nunca lanza: lo que no es un spec
 * vuelve como `ok: false`. Solo mira el spec; los datos del estado los rellena
 * el servidor aparte.
 */
export function validateCanvasSpec(input: unknown): CanvasSpecResult {
  if (!isRecord(input) || typeof input.root !== 'string' || !isRecord(input.elements)) {
    return { ok: false, issues: [{ code: 'invalid_spec', message: 'El spec debe ser { root: string, elements: { clave: elemento } }.' }] };
  }
  const issues: CanvasSpecIssue[] = [];
  const elements = input.elements as Record<string, any>;

  for (const [key, element] of Object.entries(elements)) {
    if (!isRecord(element) || typeof element.type !== 'string') {
      issues.push({ code: 'invalid_spec', element: key, message: `El elemento "${key}" necesita un type.` });
      continue;
    }
    if (Object.hasOwn(element, 'children') &&
      (!Array.isArray(element.children) || element.children.some((child: unknown) => typeof child !== 'string'))) {
      issues.push({ code: 'structure', element: key, message: `El elemento "${key}" necesita children como arreglo de strings.` });
    }
    const component = (components as Record<string, { props: z.ZodType }>)[element.type];
    if (!Object.hasOwn(components, element.type) || !component) {
      issues.push({ code: 'unknown_component', element: key, message: `El componente "${element.type}" no está en el catálogo (${COMPONENT_NAMES.join(', ')}).` });
      continue;
    }
    const parsed = component.props.safeParse(element.props ?? {});
    if (!parsed.success) {
      for (const issue of parsed.error.issues) {
        issues.push({ code: 'invalid_props', element: key, path: issue.path.join('.') || undefined, message: `${element.type}: ${issue.message}` });
      }
    }
    for (const { name, params } of bindings(element)) {
      if (typeof name !== 'string' || !(ACTION_NAMES as readonly string[]).includes(name)) {
        issues.push({ code: 'unknown_action', element: key, path: String(name), message: `La acción "${String(name)}" no está en el catálogo (${ACTION_NAMES.join(', ')}).` });
      } else if (Object.hasOwn(actions, name)) {
        const check = (actions as Record<string, { params: z.ZodType }>)[name].params.safeParse(params ?? {});
        if (!check.success) issues.push({ code: 'invalid_props', element: key, path: name, message: `Acción ${name}: ${check.error.issues[0].message}` });
      }
    }
  }
  if (issues.length) return { ok: false, issues };

  const structural = validateSpec(input as Parameters<typeof validateSpec>[0]);
  const errors = structural.issues.filter((i) => i.severity === 'error');
  if (errors.length) {
    return { ok: false, issues: errors.map((i) => ({ code: 'structure', element: i.elementKey, message: i.message })) };
  }
  return { ok: true, spec: input as CanvasSpec };
}

/** Texto para la descripción de `canvas_write`: qué puede pedir el modelo. */
export function canvasCatalogPrompt(): string {
  const parts = COMPONENT_NAMES.map((name) => `- ${name}: ${components[name].description}`);
  const acts = Object.entries(actions).map(([name, a]) => `- ${name}: ${a.description}`);
  return [
    'Componentes (catálogo cerrado; cualquier otro se rechaza):',
    ...parts,
    'Acciones en on.<evento> = { action, params }: setState, pushState, removeState, validateForm (locales, sin red) y:',
    ...acts,
    'Spec plano: { root, elements: { clave: { type, props, children?, on?, repeat? } }, state? }. Los datos van en state y las props los leen con {"$state":"/ruta"}.',
  ].join('\n');
}
