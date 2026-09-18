import type { Bundle } from "./bundle.js";
import { scanGraph } from "./graph.js";

export interface LintFinding {
  path: string;
  type?: string;
  title?: string;
}

export interface BrokenLink {
  /** Concept containing the dangling link. */
  path: string;
  /** The missing bundle-relative target. */
  target: string;
}

export interface LintReport {
  conceptCount: number;
  /** Distinct inter-concept link edges (source → target, deduped per source). */
  linkCount: number;
  /** Concepts no other concept links to (index/log catalogs don't count). */
  orphans: LintFinding[];
  /** Outbound links pointing at nonexistent concepts. */
  brokenLinks: BrokenLink[];
  healthy: boolean;
}

/**
 * Graph health check (deterministic, no LLM) — orphans + broken links,
 * Karpathy's anti-drift lint. Derived from the shared graph scan.
 */
export async function lintBundle(bundle: Bundle): Promise<LintReport> {
  const { nodes, edges, brokenLinks, inbound } = await scanGraph(bundle);

  const orphans: LintFinding[] = nodes
    .filter((n) => (inbound.get(n.path) ?? 0) === 0)
    .map((n) => ({ path: n.path, type: n.type, title: n.title }));

  return {
    conceptCount: nodes.length,
    linkCount: edges.length,
    orphans,
    brokenLinks,
    healthy: orphans.length === 0 && brokenLinks.length === 0,
  };
}
