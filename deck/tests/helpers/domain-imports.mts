import { globSync, readFileSync } from 'node:fs';
import ts from 'typescript';
import path from 'node:path';

const SRC = path.resolve(import.meta.dirname, '../../server/src');

/**
 * Node's domains: every module of server/src that sees only ports, types and rules. What they need
 * from outside comes in as a parameter. The list is the inverse: a new file is domain by default,
 * and only leaves the guard if it is in `ADAPTERS`, with its reason. The chat adds its adapters
 * (the session manager, the model proxy, the SDK of pi) here as it arrives.
 */
export const ADAPTERS = [
  // Composition: builds the adapters and reads the config.
  'index.ts', 'app.ts', 'startup.ts', 'store/index.ts',
  // Express: the thin HTTP layer.
  'api/', 'daemon-proxy.ts',
  // Persistence adapters: SQLite and the memory one that passes its same contract suite.
  'store/sqlite/', 'store/memory/',
  // The daemon over HTTP and whoever builds the credentials.
  'daemon-client.ts', 'daemon-access.ts', 'identity.ts', 'service-credential.ts',
  // Who reaches a Session, judged on the HTTP request and its login (identity.ts).
  'session-owner.ts',
  // The chat: the model proxy (HTTP to llama-server), pi's SDK, host exec (HTTP to hostexecd), and the filesystem behind slots and Session roots.
  'session-proxy.ts', 'pi/sdk-client.ts', 'pi/host-exec/','session-slots/llama-slot-store.ts', 'session-roots-fs.ts', 'workspaces-fs.ts',
  // The Instance SOUL is a file on Deck's volume.
  'instance-soul-fs.ts',
  // Voice: HTTP straight to whisper-server and audiocpp-server.
  'voice/direct-voice-speech.ts',
];

/** A daemon adapter is named `daemon-*.ts`: the port lives in the file without the prefix. */
export function isAdapter(file: string): boolean {
  return path.posix.basename(file).startsWith('daemon-') || ADAPTERS.some((a) => (a.endsWith('/') ? file.startsWith(a) : file === a));
}

/** The domain files of server/src and shared (paths relative to server/src), or all of them with `includeAdapters`. */
export function domainFiles({ includeAdapters = false } = {}): string[] {
  const all = globSync(['**/*.ts', '../../shared/*.mts'], { cwd: SRC }).map((f) => f.split(path.sep).join('/')).sort();
  return includeAdapters ? all : all.filter((f) => !isAdapter(f));
}

/** Infrastructure forbidden to every domain (packages and Node built-ins, with or without `node:`). */
const FORBIDDEN_MODULES = [
  'fs', 'fs/promises', 'child_process', 'net', 'http', 'https', 'http2', 'dns', 'dgram', 'tls', 'os', 'worker_threads',
  'better-sqlite3', 'express', 'undici', 'node-fetch', 'ws', 'jsonwebtoken',
];

/**
 * What the list forbids to all and a domain file takes anyway, with its reason.
 * Key: domain file; value: what it is allowed (module, relative specifier, `process.env`, `fetch()`...) and why.
 */
export const ALLOWED: Record<string, Record<string, string>> = {
};

const isStringLike = (n: ts.Node): n is ts.StringLiteralLike => ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n);

/** The specifiers `import`/`export ... from`/`import()` leave at runtime: `import type` is erased and leaves no edge. */
function runtimeSpecifiers(tree: ts.SourceFile): string[] {
  const specs: string[] = [];
  const visit = (node: ts.Node): void => {
    if (ts.isImportDeclaration(node) && isStringLike(node.moduleSpecifier)) {
      const clause = node.importClause;
      const named = clause?.namedBindings;
      const onlyTypes = clause && (clause.isTypeOnly || (!clause.name && named && ts.isNamedImports(named) && named.elements.length > 0 && named.elements.every((e) => e.isTypeOnly)));
      if (!onlyTypes) specs.push(node.moduleSpecifier.text);
    } else if (ts.isExportDeclaration(node) && node.moduleSpecifier && isStringLike(node.moduleSpecifier)) {
      if (!node.isTypeOnly) specs.push(node.moduleSpecifier.text);
    } else if (ts.isCallExpression(node) && node.expression.kind === ts.SyntaxKind.ImportKeyword && node.arguments[0] && isStringLike(node.arguments[0])) {
      specs.push(node.arguments[0].text);
    }
    ts.forEachChild(node, visit);
  };
  visit(tree);
  return specs;
}

/**
 * What `source` (the file `file`, path relative to server/src) imports and a domain may not:
 * infrastructure, the global `fetch`, `process.env` or a module outside `domain`.
 * The TypeScript tree is read: a string or a comment that looks like an import does not count.
 */
export function violationsIn(file: string, source: string, domain: ReadonlySet<string>): string[] {
  const tree = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true);
  const found: string[] = [];
  for (const spec of runtimeSpecifiers(tree)) {
    if (spec.startsWith('.')) {
      const resolved = path.posix.normalize(path.posix.join(path.posix.dirname(file), spec.replace(/\.mjs$/, '.mts').replace(/\.js$/, '.ts'))).replace('../../shared/dist/', '../../shared/');
      if (!domain.has(resolved)) found.push(spec);
    } else {
      const bare = spec.replace(/^node:/, '');
      if (FORBIDDEN_MODULES.some((f) => bare === f || bare.startsWith(`${f}/`))) found.push(spec);
    }
  }
  const visit = (node: ts.Node): void => {
    if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) && node.expression.text === 'fetch') found.push('fetch()');
    if (ts.isPropertyAccessExpression(node)) {
      const [obj, name] = [node.expression.getText(tree), node.name.text];
      if (obj === 'globalThis' && name === 'fetch') found.push('globalThis.fetch');
      if (obj === 'process' && name === 'env') found.push('process.env');
    }
    ts.forEachChild(node, visit);
  };
  visit(tree);
  return [...new Set(found)];
}

/** Violations per domain file, ALLOWED already discounted. `{}` is a clean tree. */
export function domainViolations(): Record<string, string[]> {
  const files = domainFiles();
  const domain = new Set(files);
  const out: Record<string, string[]> = {};
  for (const file of files) {
    const allowed = ALLOWED[file] ?? {};
    const bad = violationsIn(file, readFileSync(path.join(SRC, file), 'utf8'), domain).filter((v) => !(v in allowed));
    if (bad.length) out[file] = bad;
  }
  return out;
}
