import type { BrowserDriver } from "../browser-driver.js";
import type { SessionBrowserState } from "../session-browser.js";

/**
 * The driver's tools the Agent never gets, whatever the catalogue offers:
 *
 * - `browser_run_code_unsafe`: arbitrary JavaScript in a browser signed into the Agent's accounts is
 *   a different thing from arbitrary JavaScript in a blank one.
 * - `browser_file_upload`, `browser_drop`: they take `paths` read by the Playwright process, a child
 *   of Deck; Playwright says its cwd check is not a security boundary, so Deck's own files could end
 *   up on a web page.
 */
export const EXCLUDE_TOOLS: readonly string[] = ["browser_run_code_unsafe", "browser_file_upload", "browser_drop"];

export interface SessionBrowserToolsOptions {
  /** Filled with the name of every tool registered, so the Guard and the taint can tell these from any other tool. */
  owned?: Set<string>;
  /** The driver could not list its tools; the Session carries on without browser tools. */
  onError?: (error: Error) => void;
}

interface TextPart {
  type: "text";
  text: string;
}
const isText = (part: unknown): part is TextPart =>
  typeof part === "object" && part !== null && (part as { type?: unknown }).type === "text";

/**
 * The Agent's browser tools for one Session: Playwright's, driven over CDP on the Instance browser.
 * Registered inline, with no `mcp.json`. An ExtensionFactory.
 *
 * The Guard already gates these calls; the gate is read again here so that a tool never reaches the
 * browser when the Session may not drive it, whatever the order of the hooks.
 */
export function sessionBrowserTools(
  driver: BrowserDriver,
  gate: () => Promise<SessionBrowserState>,
  options: SessionBrowserToolsOptions = {},
) {
  return async (pi: any): Promise<void> => {
    let catalogue;
    try {
      catalogue = await driver.catalogue();
    } catch (e) {
      // Fails closed: no tools registered, so the Guard (which owns none) refuses every browser call.
      options.onError?.(e as Error);
      return;
    }
    for (const spec of catalogue) {
      if (EXCLUDE_TOOLS.includes(spec.name)) continue;
      options.owned?.add(spec.name);
      pi.registerTool({
        name: spec.name,
        label: spec.name.replaceAll("_", " "),
        description: spec.description ?? spec.name,
        parameters: spec.inputSchema,
        async execute(_id: string, params: Record<string, unknown>) {
          const state = await gate();
          if (!state.allowed || !state.cdpEndpoint) throw new Error("This Session has no browser it may drive.");
          const result = await driver.call(state.cdpEndpoint, spec.name, params ?? {});
          if (result.isError) throw new Error(textOf(result.content) || `${spec.name} failed`);
          return { content: result.content, details: {} };
        },
      });
    }
  };
}

const textOf = (content: unknown[]): string => content.filter(isText).map((part) => part.text).join("\n");
