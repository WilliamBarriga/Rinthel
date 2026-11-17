/**
 * Shared error model of every `fetch` adapter:
 * `401` = the session is not valid (go to the login), `502` = the daemon is
 * down (a notice of its own), anything else passes with its body. Controllers
 * turn a `PortError` into an error state; a view never sees a throw.
 */
export type PortErrorKind = "unauthorized" | "unavailable" | "network" | "http";

export class PortError extends Error {
  constructor(
    readonly kind: PortErrorKind,
    readonly status: number,
    message: string,
    readonly body?: unknown,
  ) {
    super(message);
    this.name = "PortError";
  }
}

export type FetchLike = typeof fetch;

/** The real `fetch`, looked up on each call so nothing global is captured or patched. */
export const globalFetch: FetchLike = (...args) => globalThis.fetch(...args);

/** The `kind` a response status gets, for every adapter that builds a `PortError` from one. */
export function kindOf(status: number): PortErrorKind {
  if (status === 401) return "unauthorized";
  if (status === 502) return "unavailable";
  return "http";
}

/** The session is not valid (`401`): the one failure that leads to the login. */
export const isUnauthorized = (e: unknown): e is PortError => e instanceof PortError && (e.kind === "unauthorized" || e.status === 401);

/** JSON request through an injected `fetch`; rejects with a `PortError` on any failure. */
export async function requestJson<T>(fetchImpl: FetchLike, url: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    // Multipart needs fetch to choose its boundary; JSON keeps the existing default.
    res = await fetchImpl(url, { ...init, headers: init?.body instanceof FormData ? init.headers : { "Content-Type": "application/json", ...init?.headers } });
  } catch (e) {
    throw new PortError("network", 0, e instanceof Error ? e.message : String(e));
  }
  if (!res.ok) {
    const body: unknown = await res.json().catch(() => undefined);
    // Node returns `error`; FastAPI returns `detail`, with a message for typed errors.
    const fields = body as { error?: unknown; detail?: unknown } | undefined;
    const detail = fields?.detail;
    const daemonMessage = typeof detail === "object" && detail !== null ? (detail as { message?: unknown }).message : detail;
    const message = typeof fields?.error === "string" && fields.error ? fields.error : daemonMessage;
    throw new PortError(kindOf(res.status), res.status, typeof message === "string" && message ? message : `HTTP ${res.status}`, body);
  }
  if (res.status === 204) return undefined as T;
  try {
    return (await res.json()) as T;
  } catch {
    throw new PortError("http", res.status, "Invalid JSON response");
  }
}

/** The text of anything a controller caught, for its error state. */
export const messageOf = (e: unknown): string => (e instanceof Error ? e.message : String(e));

/** What a view shows when a port failed; the view never sees a throw. */
export interface ViewError {
  kind: PortErrorKind | "unknown";
  message: string;
}

export const toViewError = (e: unknown): ViewError =>
  e instanceof PortError ? { kind: e.kind, message: e.message } : { kind: "unknown", message: messageOf(e) };
