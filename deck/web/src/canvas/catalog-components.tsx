import { useId, useMemo, type ReactNode } from "react";
import { useBoundProp, type ComponentContext } from "@json-render/react";
import { Streamdown } from "streamdown";
import type { canvasCatalog, ComponentName } from "@deck/canvas-catalog";

/**
 * Presentation of each component in the closed Canvas catalog. Pure views: they
 * read resolved props and emit events; the data comes from the state of the spec
 * and the effects (ask the agent) from the registry's handlers. Nothing
 * here fetches or knows about the daemon.
 */
type Catalog = typeof canvasCatalog;
type Ctx<K extends ComponentName> = ComponentContext<Catalog, K>;

const HEADING_TAGS = { 1: "h1", 2: "h2", 3: "h3" } as const;
const HEADING_SIZE = { 1: "text-xl", 2: "text-lg", 3: "text-base" } as const;
const GAP = { sm: "gap-1.5", md: "gap-3", lg: "gap-5" } as const;

const fieldClass =
  "rounded-lg border border-line bg-surface px-2.5 py-1.5 text-sm text-fg placeholder:text-fg-faint focus:border-accent focus:outline-none";

export function Heading({ props }: Ctx<"Heading">) {
  const level = (props.level ?? 2) as 1 | 2 | 3;
  const Tag = HEADING_TAGS[level];
  return <Tag className={`${HEADING_SIZE[level]} font-semibold text-fg`}>{props.text}</Tag>;
}

// A catalog Text is prose, not a way out of the Canvas: no links, no images, no raw markup.
const BLOCKED = ["a", "img", "script", "style", "iframe", "object", "embed", "form", "input"];
export function Text({ props }: Ctx<"Text">) {
  return (
    <div className="prose prose-sm max-w-none text-fg">
      <Streamdown disallowedElements={BLOCKED} unwrapDisallowed>
        {String(props.content ?? "")}
      </Streamdown>
    </div>
  );
}

export function Metric({ props }: Ctx<"Metric">) {
  return (
    <div className="inline-flex flex-col rounded-lg bg-fg/5 px-3 py-2">
      <span className="text-[11px] uppercase tracking-wide text-fg-subtle">{props.label}</span>
      <span className="text-2xl font-semibold text-fg">{String(props.value)}</span>
      {props.detail ? <span className="text-xs text-fg-muted">{props.detail}</span> : null}
    </div>
  );
}

export function Card({ props, children }: Ctx<"Card">) {
  return (
    <section className="flex flex-col gap-3 rounded-xl border border-line bg-surface p-4">
      {props.title ? <h3 className="text-sm font-semibold text-fg">{props.title}</h3> : null}
      {children}
    </section>
  );
}

export function Stack({ props, children }: Ctx<"Stack">) {
  const direction = props.direction ?? "vertical";
  return (
    <div data-stack={direction} className={`flex ${direction === "horizontal" ? "flex-row flex-wrap items-start" : "flex-col"} ${GAP[props.gap ?? "md"]}`}>
      {children}
    </div>
  );
}

export function Button({ props, emit }: Ctx<"Button">) {
  const primary = props.variant === "primary";
  return (
    <button
      type="button"
      onClick={() => emit("press")}
      className={`self-start rounded-lg px-3 py-1.5 text-sm font-medium ${primary ? "bg-accent text-canvas" : "border border-line text-fg hover:bg-fg/5"}`}
    >
      {props.label}
    </button>
  );
}

const cellText = (v: unknown) => (v === null || v === undefined ? "" : String(v));

export function Table({ props }: Ctx<"Table">) {
  const columns = props.columns ?? [];
  const needle = cellText(props.filter).trim().toLowerCase();
  const rows = useMemo(() => {
    const all = Array.isArray(props.rows) ? (props.rows as Record<string, unknown>[]) : [];
    if (!needle) return all;
    return all.filter((row) => columns.some((c) => cellText(row[c.key]).toLowerCase().includes(needle)));
  }, [props.rows, needle, columns]);
  return (
    <div className="overflow-x-auto rounded-xl border border-line">
      <table className="w-full text-left text-sm">
        <thead className="bg-fg/5 text-xs text-fg-muted">
          <tr>
            {columns.map((c) => (
              <th key={c.key} scope="col" className="px-3 py-2 font-medium">
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-t border-line">
              {columns.map((c) => (
                <td key={c.key} className="px-3 py-2 text-fg">
                  {cellText(row[c.key])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length === 0 ? <p className="px-3 py-3 text-sm text-fg-subtle">Sin filas.</p> : null}
    </div>
  );
}

function Field({ label, id, children }: { label: string; id: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-xs font-medium text-fg-muted">
        {label}
      </label>
      {children}
    </div>
  );
}

export function TextField({ props, bindings }: Ctx<"TextField">) {
  const id = useId();
  const [value, setValue] = useBoundProp<string>(props.value as string | undefined, bindings?.value);
  return (
    <Field label={props.label} id={id}>
      <input
        id={id}
        type={props.inputType ?? "text"}
        className={fieldClass}
        placeholder={props.placeholder ?? undefined}
        value={value ?? ""}
        onChange={(e) => setValue(e.target.value)}
      />
    </Field>
  );
}

export function SelectField({ props, bindings }: Ctx<"SelectField">) {
  const id = useId();
  const [value, setValue] = useBoundProp<string>(props.value as string | undefined, bindings?.value);
  return (
    <Field label={props.label} id={id}>
      <select id={id} className={fieldClass} value={value ?? ""} onChange={(e) => setValue(e.target.value)}>
        {(props.options ?? []).map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </Field>
  );
}

export function CheckboxField({ props, bindings }: Ctx<"CheckboxField">) {
  const id = useId();
  const [value, setValue] = useBoundProp<boolean>(props.value as boolean | undefined, bindings?.value);
  return (
    <label htmlFor={id} className="inline-flex items-center gap-2 text-sm text-fg">
      <input id={id} type="checkbox" checked={!!value} onChange={(e) => setValue(e.target.checked)} />
      {props.label}
    </label>
  );
}
