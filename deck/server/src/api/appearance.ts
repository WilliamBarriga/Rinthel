import { AppearanceValidationError, AppearanceAccessError } from "../../../shared/dist/appearance.mjs";
import express from "express";
import type { SettingsRepo } from "../store/port.js";
import { appearanceSettings } from "../appearance.js";
import { identityOf, isAdminIdentity } from "../identity.js";
import { adminOnly } from "./admin-only.js";

/** Mounted after requireAuth. The caller never supplies a user key. */
export function appearanceRouter(settings: SettingsRepo) {
  const router = express.Router(); const appearance = appearanceSettings(settings);
  router.get("/appearance", async (req, res) => {
    try { res.json(await appearance.read(identityOf(req)?.userId ?? null, isAdminIdentity(identityOf(req)))); }
    catch (error) { res.status(error instanceof AppearanceValidationError || error instanceof SyntaxError ? 409 : 500).json({ error: "No se pudo leer la configuración de apariencia. No se ha sobrescrito." }); }
  });
  router.put("/appearance", async (req, res) => {
    try { res.json(await appearance.save(identityOf(req)?.userId ?? null, req.body, isAdminIdentity(identityOf(req)))); }
    catch (error) { res.status(error instanceof AppearanceAccessError ? 403 : error instanceof AppearanceValidationError ? 400 : 500).json({ error: error instanceof AppearanceValidationError ? error.message : "No se pudo guardar la apariencia." }); }
  });
  router.put("/appearance/brand", adminOnly("la marca", "Solo el administrador puede cambiar la marca de instalación."), async (req, res) => {
    try { res.json(await appearance.brand(req.body, true)); }
    catch (error) { res.status(error instanceof AppearanceValidationError ? 400 : 500).json({ error: error instanceof AppearanceValidationError ? error.message : "No se pudo guardar la marca." }); }
  });
  return router;
}
