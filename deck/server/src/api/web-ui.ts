import { existsSync } from "node:fs";
import path from "node:path";
import express, { type Express } from "express";

/**
 * The built web UI, when there is one: its files, and `index.html` for every path that is not
 * `/api` (the single-page app routes on its own). Mounted last, so a route above always wins.
 * Returns whether `dist` existed: without a build the server is an API only.
 */
export function mountWebUi(app: Express, dist: string): boolean {
  if (!existsSync(dist)) return false;
  app.use(express.static(dist));
  app.get(/^(?!\/api).*/, (_req, res) => res.sendFile(path.join(dist, "index.html")));
  return true;
}
