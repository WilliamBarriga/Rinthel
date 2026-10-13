import { existsSync } from "node:fs";
import { resolve } from "node:path";

/**
 * The portal loads the mounted subagents extension only when it is configured.
 * Unlike host exec it needs no token, and a missing mount just means no
 * `subagent` tool — the session itself still starts.
 */
export function subagentExtensionPaths(): string[] {
  const path = process.env.RINTHEL_SUBAGENTS_EXTENSION?.trim();
  if (!path) return [];
  const absolute = resolve(path);
  if (!existsSync(absolute)) {
    console.error(`[portal] subagents extension not mounted: ${absolute}`);
    return [];
  }
  return [absolute];
}
