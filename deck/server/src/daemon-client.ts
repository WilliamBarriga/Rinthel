/**
 * The one way Node reaches the Rinthel daemon (the daemon owns the users, Node
 * only asks). A port: `fetchDaemonClient` is the real adapter; the tests use a
 * double of the daemon (`tests/helpers/fake-daemon.mts`).
 *
 * Three modes, one per way the daemon authenticates a caller (ADR 0003):
 *  - `asService()`: the shared service secret, no user behind the call.
 *  - `actingAs(userId)`: the service acting for a user (`service_as_user`);
 *    the daemon reads the user only from `X-Rinthel-User-Id`, never the body.
 *  - `withPanelToken(token)`: the logged-in user's own Panel token as a Bearer.
 *
 * The interface is `fetch` over the daemon's paths: the caller never sees the
 * URL or the credentials, and cannot override them with its own headers.
 * A daemon that answers with an error is a `Response`; one that does not
 * answer rejects the call.
 */
export interface DaemonCaller {
  /** `path` is the daemon's (`/identity/users?x=1`); `init` is a plain `fetch` init. */
  fetch(path: string, init?: RequestInit): Promise<Response>;
}

/** The `detail` of the daemon's 401 for a user who is disabled, deleted or unnamed (`service_as_user`, rinthel `api/access.py`). */
export const USER_NOT_AVAILABLE = "invalid or missing X-Rinthel-User-Id";

/**
 * Whether an `actingAs` call met the daemon's 401 for a user who is not available, told apart from the same status for
 * a rejected service credential. It reads the body.
 */
export async function userNotAvailable(res: Response): Promise<boolean> {
  if (res.status !== 401) return false;
  const detail = await res.json().then((body: { detail?: unknown }) => body?.detail, () => undefined);
  return detail === USER_NOT_AVAILABLE;
}

export interface DaemonClient {
  asService(): DaemonCaller;
  actingAs(userId: number): DaemonCaller;
  withPanelToken(token: string): DaemonCaller;
}

export interface DaemonEndpoint {
  url: string;
  serviceSecret: string;
}

type Credentials = { mode: "service" } | { mode: "user"; userId: number } | { mode: "panel"; token: string };

const CREDENTIAL_HEADERS = ["authorization", "x-rinthel-service-secret", "x-rinthel-user-id"];

/**
 * What goes on the wire for a mode: the caller's headers with the
 * credentials replaced, whatever the caller tried to send in their place.
 */
export function withCredentials(
  credentials: Credentials,
  serviceSecret: string,
  callerHeaders: HeadersInit | undefined,
): Headers {
  const headers = new Headers(callerHeaders);
  for (const name of CREDENTIAL_HEADERS) headers.delete(name);
  if (credentials.mode === "panel") {
    headers.set("authorization", `Bearer ${credentials.token}`);
  } else {
    headers.set("x-rinthel-service-secret", serviceSecret);
    if (credentials.mode === "user") headers.set("x-rinthel-user-id", String(credentials.userId));
  }
  return headers;
}

export function fetchDaemonClient({ url, serviceSecret }: DaemonEndpoint): DaemonClient {
  const base = url.replace(/\/+$/, "");
  const caller = (credentials: Credentials): DaemonCaller => ({
    fetch: (path, init = {}) =>
      fetch(`${base}${path}`, { ...init, headers: withCredentials(credentials, serviceSecret, init.headers) }),
  });
  return {
    asService: () => caller({ mode: "service" }),
    actingAs: userId => caller({ mode: "user", userId }),
    withPanelToken: token => caller({ mode: "panel", token }),
  };
}
