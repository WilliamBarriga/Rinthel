import { readFileSync, existsSync } from 'node:fs';
import path from 'node:path';

const SRC = path.resolve(import.meta.dirname, '../../server/src');

/** Relative value imports of a module (`import type` is erased, so it makes no runtime edge). */
function importsOf(file: string): string[] {
  const text = readFileSync(file, 'utf8');
  const found: string[] = [];
  for (const m of text.matchAll(/(?:^|\n)\s*(?:import|export)\s+(type\s+)?[^;'"]*?from\s+["'](\.[^"']+)["']|import\(\s*["'](\.[^"']+)["']\s*\)|(?:^|\n)\s*import\s+["'](\.[^"']+)["']/g)) {
    if (m[1]) continue;
    const spec = m[2] ?? m[3] ?? m[4];
    const resolved = path.resolve(path.dirname(file), spec.replace(/\.js$/, '.ts'));
    const candidates = [resolved, resolved + '.ts', path.join(resolved, 'index.ts')];
    const hit = candidates.find((c) => c.endsWith('.ts') && existsSync(c));
    if (hit) found.push(hit);
  }
  return found;
}

/** Every import cycle (as a list of src-relative paths) in the server's runtime import graph. */
export function importCycles(): string[][] {
  const graph = new Map<string, string[]>();
  const walk = (file: string) => {
    if (graph.has(file)) return;
    graph.set(file, []);
    const deps = importsOf(file);
    graph.set(file, deps);
    deps.forEach(walk);
  };
  walk(path.join(SRC, 'index.ts'));

  const cycles: string[][] = [];
  const seen = new Set<string>();
  const stack: string[] = [];
  const done = new Set<string>();
  const visit = (file: string) => {
    if (done.has(file)) return;
    const at = stack.indexOf(file);
    if (at >= 0) {
      const cycle = stack.slice(at).map((f) => path.relative(SRC, f));
      const key = [...cycle].sort().join('|');
      if (!seen.has(key)) { seen.add(key); cycles.push(cycle); }
      return;
    }
    stack.push(file);
    for (const dep of graph.get(file) ?? []) visit(dep);
    stack.pop();
    done.add(file);
  };
  [...graph.keys()].forEach(visit);
  return cycles;
}
