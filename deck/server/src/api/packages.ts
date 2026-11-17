import express, { type Response, type Router } from "express";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { PACKAGE_SPEC, type PiPackages } from "../pi-packages.js";
import { adminOnly } from "./admin-only.js";

/** What the packages routes reach: pi's packages in Deck's agentDir, and pi's settings file there. */
export interface PackagesDeps {
  packages: PiPackages;
  /** `<agentDir>/settings.json`, where extensions read their configuration. */
  settingsFile: string;
}

/**
 * The extras of Deck's agentDir, admin only (reading included); a member is a `403` before pi runs.
 *
 * - `GET /packages`, `POST /packages {spec}`, `DELETE /packages {spec}`, `POST /packages/update`: pi's
 *   package manager. A spec that is not one of pi's documented shapes is a `400`; pi failing is a `502`
 *   with its own words. Installed packages load in admin Sessions started afterwards.
 * - `GET`/`PUT /pi-settings`: pi's settings file, raw. Extensions configure themselves there and pi
 *   exposes no schema, so the file is edited as is; content pi could not parse is refused and never
 *   written (a broken file stops every later Session).
 */
export function packagesRouter({ packages, settingsFile }: PackagesDeps): Router {
  const router = express.Router();
  router.use(["/packages", "/pi-settings"], adminOnly("los paquetes"));

  const run = async (res: Response, call: () => Promise<string>) => {
    try {
      res.json({ ok: true, output: (await call()).trim() });
    } catch (e) {
      res.status(502).json({ error: (e as Error).message });
    }
  };
  const specOf = (body: unknown): string | null => {
    const spec = (body as { spec?: unknown } | undefined)?.spec;
    return typeof spec === "string" && PACKAGE_SPEC.test(spec) ? spec : null;
  };
  const badSpec = (res: Response) =>
    res.status(400).json({ error: "El paquete debe tener la forma npm:pkg@1.0.0, git:github.com/user/repo, https://… o una ruta" });

  router.get("/packages", (_req, res) => run(res, () => packages.list()));

  router.post("/packages", async (req, res) => {
    const spec = specOf(req.body);
    if (!spec) return badSpec(res);
    await run(res, () => packages.install(spec));
  });

  router.delete("/packages", async (req, res) => {
    const spec = specOf(req.body);
    if (!spec) return badSpec(res);
    await run(res, () => packages.remove(spec));
  });

  router.post("/packages/update", (_req, res) => run(res, () => packages.update()));

  router.get("/pi-settings", (_req, res) => {
    try {
      res.json({ path: settingsFile, content: existsSync(settingsFile) ? readFileSync(settingsFile, "utf8") : "{}\n" });
    } catch (e) {
      res.status(500).json({ error: (e as Error).message });
    }
  });

  router.put("/pi-settings", (req, res) => {
    const content = req.body?.content;
    if (typeof content !== "string") return res.status(400).json({ error: "content required" });
    try {
      JSON.parse(content);
    } catch (e) {
      return res.status(400).json({ error: `No es JSON válido: ${(e as Error).message}` });
    }
    try {
      mkdirSync(path.dirname(settingsFile), { recursive: true });
      writeFileSync(settingsFile, content, "utf8");
      res.json({ ok: true, path: settingsFile });
    } catch (e) {
      res.status(500).json({ error: (e as Error).message });
    }
  });

  return router;
}
