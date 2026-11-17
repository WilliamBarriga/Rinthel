import express, { type Router } from "express";
import type { InstanceSoul as InstanceSoulBody } from "@deck/contract";
import { identityOf, isAdminIdentity } from "../identity.js";
import { MAX_SOUL_CHARS, type InstanceSoul } from "../instance-soul.js";
import { adminOnly } from "./admin-only.js";

/**
 * The Instance SOUL: the `SOUL.md` every member's Sessions load. Anyone logged in reads it (a member
 * sees what their Agent is told it is, read-only); only an admin, by the role the Instance has now,
 * replaces it. The admin's own `SOUL.md`, for their own Sessions, is a different file and not here.
 */
export function instanceSoulRouter(soul: InstanceSoul): Router {
  const router = express.Router();
  const body = (editable: boolean): InstanceSoulBody => {
    const content = soul.read();
    return { name: "SOUL.md", exists: content !== null, content: content ?? "", editable };
  };
  router.get("/agent/instance-soul", (req, res) => res.json(body(isAdminIdentity(identityOf(req)))));
  router.put("/agent/instance-soul", adminOnly("la SOUL de la Instance"), (req, res) => {
    const content = req.body?.content;
    if (typeof content !== "string") return void res.status(400).json({ error: "content required" });
    if (content.length > MAX_SOUL_CHARS) return void res.status(400).json({ error: `La SOUL no puede pasar de ${MAX_SOUL_CHARS} caracteres` });
    soul.write(content);
    res.json(body(true));
  });
  return router;
}
