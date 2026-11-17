/**
 * A hostexecd as Deck reaches it, over real HTTP: `POST /exec` and `GET /history` behind the
 * `X-Rinthel-Token` header (`401` without the right one), with the same answer shapes as
 * `rinthel/hostexecd/daemon.py`. Nothing runs: `/exec` answers `result` and records the request, so a
 * test sees exactly what reached the host and with which token.
 */
import { listen, readJson, sendJson as json } from "./http-fake.mts";

export interface ExecRequest { command: string; cwd: string | null; timeout: number | null }

export interface FakeHostexecd {
  url: string;
  token: string;
  /** Every authorised `/exec`, in order. */
  execs: ExecRequest[];
  /** Every request that reached it, authorised or not: `METHOD /path`. */
  requests: string[];
  /** What `/exec` answers. */
  result: { exit_code: number; stdout: string; stderr: string; duration_ms: number; timed_out: boolean };
  /** What `/history` answers, most recent first. */
  history: { ts: number; command: string; cwd: string | null; exit_code: number; duration_ms: number; stdout_len: number; stderr_len: number; timed_out: boolean }[];
  close(): Promise<void>;
}

export async function fakeHostexecd(token = "hostexec-test-token"): Promise<FakeHostexecd> {
  const state: Omit<FakeHostexecd, "url" | "close"> = {
    token,
    execs: [],
    requests: [],
    result: { exit_code: 0, stdout: "ok\n", stderr: "", duration_ms: 3, timed_out: false },
    history: [],
  };
  const server = await listen(async (req, res) => {
    const url = new URL(req.url ?? "/", "http://hostexecd");
    const body = await readJson(req);
    state.requests.push(`${req.method} ${url.pathname}`);
    if (url.pathname === "/health") return json(res, 200, { ok: true });
    if (req.headers["x-rinthel-token"] !== state.token) return json(res, 401, { detail: "invalid or missing token" });
    if (req.method === "POST" && url.pathname === "/exec") {
      state.execs.push({ command: body.command, cwd: body.cwd ?? null, timeout: body.timeout ?? null });
      return json(res, 200, state.result);
    }
    if (req.method === "GET" && url.pathname === "/history") {
      const limit = Number(url.searchParams.get("limit") ?? 20);
      return json(res, 200, { entries: state.history.slice(0, limit) });
    }
    json(res, 404, { detail: "Not Found" });
  });
  return Object.assign(state, { url: server.url, close: server.close });
}
