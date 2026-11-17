/**
 * The Rinthel daemon's identity area as Deck reaches it: a `DaemonClient` (the port Node talks to the
 * daemon through) with no network and no database. The real Deck server code runs on top of it, so
 * everything Node does with the daemon's answers is real; only the daemon's side is scripted here,
 * with its rules: login, a refresh token that rotates on each use, logout that revokes it, the users
 * an admin manages (with the last-admin and self-lockout guards) and `session-principal` for the
 * service acting as a user; and the Local models: the catalog and the switch (admin, `409
 * lifecycle_busy`/`turns_in_flight` while `switchRefusal` says so) and `GET /model-provider/routing`
 * (service), whose `llm` route points at `llamaUrl` and whose `understory_url` is `understoryUrl`.
 */
import jwt from "jsonwebtoken";
import { randomBytes } from "node:crypto";
import type { DaemonCaller, DaemonClient } from "../../server/src/daemon-client.ts";
import { USER_NOT_AVAILABLE } from "../../server/src/daemon-client.ts";
import type { Role, UserPublic } from "../../shared/contract/index.ts";

type Reply = { status: number; body?: unknown };
type User = UserPublic & { password: string };
type Caller = { kind: "service"; actingAs: number | null } | { kind: "panel"; token: string };

const ok = (body: unknown): Reply => ({ status: 200, body });
const unauthorized = (detail = "Unauthorized"): Reply => ({ status: 401, body: { detail } });
const conflict = (code: string, message: string): Reply => ({ status: 409, body: { detail: { code, message } } });

export class FakeDaemon implements DaemonClient {
  private users = new Map<number, User>();
  private nextId = 1;
  /** Live refresh tokens and whose they are. */
  private refreshTokens = new Map<string, number>();
  /** How long a minted access token lives, in seconds; a test shortens it to make one expire. */
  accessTtl = 3600;
  /** Whether the daemon answers at all. */
  down = false;
  /** Every call that reached the daemon, as `METHOD /path`. */
  readonly calls: string[] = [];
  /** The Local model catalog (`llm` entries) and the active one. */
  models: { id: string; context_window: number }[] = [];
  activeModel: string | null = null;
  /** Where the `llm` route points; without it there is no route. */
  llamaUrl: string | null = null;
  /** Where the routing says Understory is; `null` is Understory off. */
  understoryUrl: string | null = null;
  /** The daemon's own refusal of the next switches (`lifecycle_busy`, `turns_in_flight`). */
  switchRefusal: string | null = null;

  constructor(private readonly panelSecret: string) {}

  /** A user the daemon knows; returns its id. */
  addUser(username: string, password: string, role: Role = "miembro"): number {
    const id = this.nextId++;
    this.users.set(id, { id, username, password, role, notes: "", created_at: new Date().toISOString(), disabled: false });
    return id;
  }

  disable(id: number): void {
    const user = this.users.get(id);
    if (user) user.disabled = true;
  }

  has(id: number): boolean {
    return this.users.has(id);
  }

  /** An access token as the daemon signs it, valid for `ttl` seconds (negative: already expired). */
  accessToken(id: number, ttl = this.accessTtl): string {
    const u = this.users.get(id)!;
    // A `jti` per token: two signed in the same second are still two logins (a logout revokes one).
    return jwt.sign({ sub: String(u.id), username: u.username, role: u.role, typ: "access" }, this.panelSecret, { algorithm: "HS256", expiresIn: ttl, jwtid: randomBytes(8).toString("hex") });
  }

  asService = (): DaemonCaller => this.caller({ kind: "service", actingAs: null });
  actingAs = (userId: number): DaemonCaller => this.caller({ kind: "service", actingAs: userId });
  withPanelToken = (token: string): DaemonCaller => this.caller({ kind: "panel", token });

  private caller(who: Caller): DaemonCaller {
    return {
      fetch: async (path, init = {}) => {
        if (this.down) throw new TypeError("fetch failed");
        const url = new URL(path, "http://daemon");
        const method = (init.method ?? "GET").toUpperCase();
        this.calls.push(`${method} ${url.pathname}`);
        const body = typeof init.body === "string" && init.body ? JSON.parse(init.body) : {};
        const reply = this.handle(method, url.pathname, body, who);
        return new Response(JSON.stringify(reply.body ?? {}), { status: reply.status, headers: { "content-type": "application/json" } });
      },
    };
  }

  private session(u: User) {
    const refresh = randomBytes(16).toString("hex");
    this.refreshTokens.set(refresh, u.id);
    return { access_token: this.accessToken(u.id), refresh_token: refresh, access_expires_in: this.accessTtl, user: { id: u.id, username: u.username, role: u.role } };
  }

  /** The `admin` policy: a Bearer Panel token whose user is an active admin now. */
  private admin(who: Caller): User | Reply {
    if (who.kind !== "panel") return unauthorized("missing bearer token");
    let sub: number;
    try {
      sub = Number((jwt.verify(who.token, this.panelSecret, { algorithms: ["HS256"] }) as jwt.JwtPayload).sub);
    } catch {
      return unauthorized("invalid token");
    }
    const user = this.users.get(sub);
    if (!user || user.disabled) return unauthorized("invalid token");
    if (user.role !== "admin") return { status: 403, body: { detail: "admin required" } };
    return user;
  }

  private publicView({ password: _password, ...u }: User): UserPublic {
    return { ...u };
  }

  /** The last-admin and self-lockout guards, for a change that takes `target`'s admin away. */
  private guard(acting: User, target: User): Reply | null {
    if (target.role !== "admin" || target.disabled) return null;
    if (target.id === acting.id) return conflict("self_lockout", "an admin cannot disable, demote or delete themselves");
    if ([...this.users.values()].filter((u) => u.role === "admin" && !u.disabled).length === 1) return conflict("last_admin", "the Instance needs an active admin");
    return null;
  }

  private handle(method: string, path: string, body: any, who: Caller): Reply {
    if (method === "POST" && path === "/identity/login") {
      const user = [...this.users.values()].find((u) => u.username === body.username && u.password === body.password && !u.disabled);
      return user ? ok(this.session(user)) : unauthorized("invalid credentials");
    }
    if (method === "POST" && path === "/identity/refresh") {
      const id = this.refreshTokens.get(body.refresh_token);
      this.refreshTokens.delete(body.refresh_token);
      const user = id === undefined ? undefined : this.users.get(id);
      return user && !user.disabled ? ok(this.session(user)) : unauthorized("invalid refresh token");
    }
    if (method === "POST" && path === "/identity/logout") {
      this.refreshTokens.delete(body.refresh_token);
      return ok({ ok: true });
    }
    if (method === "GET" && path === "/identity/me/session-principal") {
      if (who.kind !== "service") return unauthorized("invalid or missing service secret");
      const user = who.actingAs === null ? undefined : this.users.get(who.actingAs);
      if (!user || user.disabled) return unauthorized(USER_NOT_AVAILABLE);
      return ok({ user_id: user.id, role: user.role });
    }
    if (method === "GET" && path === "/model-provider/routing") {
      if (who.kind !== "service") return unauthorized("invalid or missing service secret");
      const model = this.models.find((m) => m.id === this.activeModel);
      return ok({ capabilities: model && this.llamaUrl ? { llm: { url: this.llamaUrl, model: model.id, context_window: model.context_window, reasoning_format: "qwen-chat-template" } } : {}, understory_url: this.understoryUrl });
    }
    if (path === "/models" || path === "/models/activate") {
      const acting = this.admin(who);
      if ("status" in acting) return acting;
      if (method === "GET" && path === "/models") {
        return ok({
          active: { llm: this.activeModel, stt: null, tts: null },
          models: this.models.map((m) => ({ id: m.id, name: m.id, capability: "llm", activable: true, problem: null, context_window: m.context_window, reasoning_format: "qwen-chat-template" })),
        });
      }
      if (method === "POST" && path === "/models/activate") {
        if (this.switchRefusal) return { status: 409, body: { detail: this.switchRefusal } };
        if (!this.models.some((m) => m.id === body.id)) return { status: 404, body: { detail: "unknown_model" } };
        this.activeModel = body.id;
        return ok({ ok: true, active: body.id, rolled_back: null, results: [{ service: "llama-server", ok: true, message: "listo" }], warnings: [] });
      }
    }
    if (!path.startsWith("/identity/users")) return { status: 404, body: { detail: "Not Found" } };

    const acting = this.admin(who);
    if ("status" in acting) return acting;
    if (path === "/identity/users") {
      if (method === "GET") return ok({ users: [...this.users.values()].map((u) => this.publicView(u)) });
      if (method === "POST") {
        if ([...this.users.values()].some((u) => u.username === body.username)) return conflict("username_taken", `username ${body.username} already exists`);
        const id = this.addUser(body.username, body.password, body.role);
        const user = this.users.get(id)!;
        user.notes = body.notes ?? "";
        return ok(this.publicView(user));
      }
    }
    const m = path.match(/^\/identity\/users\/(\d+)$/);
    if (!m) return { status: 404, body: { detail: "Not Found" } };
    const target = this.users.get(Number(m[1]));
    if (method === "DELETE") {
      if (!target) return ok({ ok: true });
      const refused = this.guard(acting, target);
      if (refused) return refused;
      this.users.delete(target.id);
      return ok({ ok: true });
    }
    if (method === "PATCH") {
      if (!target) return { status: 404, body: { detail: "not found" } };
      if (body.disabled === true || (body.role && body.role !== "admin")) {
        const refused = this.guard(acting, target);
        if (refused) return refused;
      }
      if (body.role) target.role = body.role;
      if (typeof body.notes === "string") target.notes = body.notes;
      if (typeof body.disabled === "boolean") target.disabled = body.disabled;
      if (typeof body.password === "string") target.password = body.password;
      return ok(this.publicView(target));
    }
    return { status: 405, body: { detail: "Method Not Allowed" } };
  }
}
