/**
 * What the admin-only tools of a Session (host exec, Memoria, subagents) share: the owner's live role
 * and how they talk about the service behind them.
 *
 * - The role is asked before every call and fails closed: a member now, a gone owner or an identity
 *   that does not answer all refuse, with the same words for every tool.
 * - A service URL is only ever http(s); anything else is refused before a request is made.
 * - A 401 from the service is a token mismatch: it needs the admin, not a retry.
 */

/** Host exec's tools (`host-exec/`); the Guard revokes both from a tainted Session. */
export const HOST_EXEC_TOOLS: readonly string[] = ["rinthel_host_exec", "rinthel_host_exec_history"];

/** Memoria's tools (`memoria/`), as the Agent sees them. */
export const MEMORIA_TOOLS: readonly string[] = ["understory_memory_query", "understory_memory_add", "understory_memory_update"];

/** What a subagent's child may call of Memoria: reading only. */
export const MEMORIA_CHILD_TOOLS: readonly string[] = ["understory_memory_query"];

/** Memoria's writes: what a tainted Session loses of it. */
export const MEMORIA_WRITE_TOOLS: readonly string[] = MEMORIA_TOOLS.filter((name) => !MEMORIA_CHILD_TOOLS.includes(name));

/** The one tool of `subagents/`. */
export const SUBAGENT_TOOL = "subagent";

/** What every admin-only tool factory gets: whether the Session's owner is an admin right now. */
export interface AdminToolAccess {
  adminNow: () => Promise<boolean>;
}

/**
 * The check an admin-only tool runs before each call: resolves when the owner is an admin now, throws
 * the refusal the Agent reads otherwise. `what` names the tool family in the refusal ("host exec is").
 */
export function adminGate(adminNow: () => Promise<boolean>, what: string): () => Promise<void> {
  return async () => {
    let admin = false;
    try {
      admin = await adminNow();
    } catch {
      admin = false;
    }
    if (!admin) throw new Error(`Refused: ${what} for an admin, and the owner of this Session is not one now (or that could not be checked).`);
  };
}

/**
 * A service's URL from `raw`, or a throw that starts with `unusable` (who is speaking: "hostexecd URL",
 * "Memoria is unavailable:"). With `path`, `raw` is a base and the URL is `path` below it.
 */
export function serviceUrl(raw: string, unusable: string, path?: string): URL {
  let url: URL;
  try {
    url = path === undefined ? new URL(raw) : new URL(path, raw.endsWith("/") ? raw : `${raw}/`);
  } catch {
    throw new Error(`${unusable} "${raw}" is not a valid URL.`);
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") throw new Error(`${unusable} "${raw}" is not http(s).`);
  return url;
}

/** The error for a 401: `service` and Deck do not share `secret`. */
export const tokenRefused = (service: string, secret: string): Error =>
  new Error(`${service} refused the token (401): Deck and ${service} do not share ${secret}. Needs the admin, not a retry.`);
