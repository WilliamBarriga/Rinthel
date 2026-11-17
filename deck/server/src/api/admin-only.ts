import type { NextFunction, Request, Response } from "express";
import { identityOf, isAdminIdentity } from "../identity.js";
import { IDENTITY_REFUSAL, identityAccess } from "../session-identity.js";
import { currentIdentity } from "./session-identity.js";

/** The `403` a member reads where only an admin may use `what`. */
export const adminRefusal = (what: string): string => `Solo el administrador puede usar ${what}.`;

/**
 * Middleware: only an admin gets through, everyone else is a `403` naming `what`. The role is the one the Instance has
 * now (`currentIdentity`), not the one in the access token: a disabled or deleted user is a `401` and an identity that
 * cannot be read a `502`, before anything runs.
 *
 * The member reads the refusal, so it is Spanish: `what` names the protected thing in Spanish, with its article and the
 * glossary's term (`la terminal`, `los usuarios`), and `refused` replaces the whole sentence when "usar" does not fit.
 */
export function adminOnly(what: string, refused = adminRefusal(what)) {
  return async (req: Request, res: Response, next: NextFunction) => {
    const access = await identityAccess(() => currentIdentity(req), () => isAdminIdentity(identityOf(req)));
    if (access === 200) return next();
    res.status(access).json({ error: access === 403 ? refused : IDENTITY_REFUSAL[access] });
  };
}
