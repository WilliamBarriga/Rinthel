import { existsSync } from "node:fs";
import { resolve } from "node:path";

/** The portal loads the mounted extension only when host exec is configured. */
export function hostExecExtensionPaths(): string[] {
  const path = process.env.RINTHEL_HOST_EXEC_EXTENSION?.trim();
  if (!path || !process.env.RINTHEL_HOSTEXECD_TOKEN?.trim()) return [];
  const absolute = resolve(path);
  if (!existsSync(absolute)) throw new Error("La extensión host exec configurada no está montada");
  return [absolute];
}
