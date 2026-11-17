import { test } from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import ts from "typescript";

const SRC = path.resolve(import.meta.dirname, "../web/src");
const walk = (dir: string): string[] => readdirSync(dir, { withFileTypes: true })
  .flatMap(entry => entry.isDirectory() ? walk(path.join(dir, entry.name)) : [path.join(dir, entry.name)]);
const parse = (file: string, source: string) => ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, file.endsWith("tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS);

/** Model folders contain pure transitions, with data-only imports across their seam. */
function modelViolations(file: string, source: string): string[] {
  const failures: string[] = [];
  const visit = (node: ts.Node) => {
    if (ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) {
      const specifier = node.moduleSpecifier;
      const typeOnly = ts.isImportDeclaration(node) ? node.importClause?.isTypeOnly
        || (!node.importClause?.name && node.importClause?.namedBindings && ts.isNamedImports(node.importClause.namedBindings)
          && node.importClause.namedBindings.elements.every(e => e.isTypeOnly)) : node.isTypeOnly;
      if (specifier && ts.isStringLiteral(specifier) && !typeOnly) {
        const target = path.resolve(path.dirname(file), specifier.text);
        if (!specifier.text.startsWith(".") || !target.startsWith(path.dirname(file) + path.sep)) failures.push(`runtime import: ${specifier.text}`);
      }
    }
    if (ts.isAwaitExpression(node) || ts.isJsxElement(node) || ts.isJsxSelfClosingElement(node)) failures.push("async/JSX in model");
    if (ts.isIdentifier(node) && ["window", "document", "navigator", "localStorage", "fetch", "setTimeout", "setInterval", "AudioContext", "WebSocket", "EventSource"].includes(node.text)) failures.push(node.text);
    ts.forEachChild(node, visit);
  };
  visit(parse(file, source));
  return failures;
}

test("frontend models remain independent of React, DOM and effect adapters", () => {
  const files = walk(SRC).filter(file => file.includes(`${path.sep}model${path.sep}`) && /\.tsx?$/.test(file) && !/\.test\.tsx?$/.test(file));
  assert.ok(files.length > 0);
  const failures = files.flatMap(file => modelViolations(file, readFileSync(file, "utf8")).map(reason => `${path.relative(SRC, file)}: ${reason}`));
  assert.deepEqual(failures, []);
});

test("the model guard detects effects and ignores comments and type-only imports", () => {
  const file = path.join(SRC, "probe/model/state.ts");
  assert.deepEqual(modelViolations(file, 'import type { T } from "react"; // fetch(url)\nconst text = "window";'), []);
  assert.ok(modelViolations(file, 'import { useState } from "react";').length > 0);
  assert.ok(modelViolations(file, 'import { api } from "../../ports/adapters/fetch-auth";').length > 0);
  assert.ok(modelViolations(file, 'const send = () => fetch("/api");').length > 0);
  assert.ok(modelViolations(path.join(SRC, "probe/model/view.tsx"), "const v = <div />;").length > 0);
});

test("presentation modules do not acquire ports or run asynchronous business actions", () => {
  const views = ["App.tsx", "home/HomePage.tsx", "shell/Sidebar.tsx", "users/UsersPage.tsx", "users/UsersTable.tsx", "users/UserDelete.tsx"];
  const failures: string[] = [];
  for (const file of views) {
    const visit = (node: ts.Node) => {
      if (ts.isImportDeclaration(node) && ts.isStringLiteral(node.moduleSpecifier) && /ports\/(context|adapters)/.test(node.moduleSpecifier.text)) failures.push(`${file}: acquires port`);
      if (ts.isAwaitExpression(node)) failures.push(`${file}: async action`);
      ts.forEachChild(node, visit);
    };
    visit(parse(file, readFileSync(path.join(SRC, file), "utf8")));
  }
  assert.deepEqual(failures, []);
});

/** View components may obtain a `*Api` port but must not call its methods: controllers do that. */
function viewApiCalls(file: string, source: string): string[] {
  const sf = parse(file, source);
  const isPortHook = (n: ts.Node | undefined): boolean => !!n && ts.isCallExpression(n) && ts.isIdentifier(n.expression) && /^use\w*Api$/.test(n.expression.text);
  const ports = new Set<string>();
  const collect = (node: ts.Node) => {
    if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && isPortHook(node.initializer)) ports.add(node.name.text);
    ts.forEachChild(node, collect);
  };
  collect(sf);
  const calls: string[] = [];
  const visit = (node: ts.Node) => {
    if (ts.isCallExpression(node)) {
      const callee = node.expression;
      if (ts.isPropertyAccessExpression(callee) && (isPortHook(callee.expression) || (ts.isIdentifier(callee.expression) && ports.has(callee.expression.text)))) {
        calls.push(`calls ${callee.expression.getText(sf)}.${callee.name.text}`);
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(sf);
  return calls;
}

/** Screens allowed to call a port from the view. Empty and pinned at 0: no TSX calls a *Api. */
const VIEW_API_EXCEPTIONS: string[] = [];

test("no view component calls a *Api port outside the shrinking exception list", () => {
  const views = walk(SRC).filter(file => file.endsWith(".tsx") && !/\.test\.tsx$/.test(file) && !file.includes(`${path.sep}ports${path.sep}`));
  const offenders = views.filter(file => viewApiCalls(file, readFileSync(file, "utf8")).length > 0).map(file => path.relative(SRC, file).split(path.sep).join("/")).sort();
  const unexpected = offenders.filter(file => !VIEW_API_EXCEPTIONS.includes(file));
  assert.deepEqual(unexpected, [], "view components must not call a *Api port; move the call to a controller hook");
  const stale = VIEW_API_EXCEPTIONS.filter(file => !offenders.includes(file));
  assert.deepEqual(stale, [], "these exceptions no longer call a port: remove them from VIEW_API_EXCEPTIONS");
});

test("the exception list has no duplicates and its size is pinned, so adding an entry fails here", () => {
  assert.equal(new Set(VIEW_API_EXCEPTIONS).size, VIEW_API_EXCEPTIONS.length);
  assert.ok(VIEW_API_EXCEPTIONS.length <= 0, "the exception list may only shrink");
});

test("the view guard flags a TSX that calls a *Api port", () => {
  const file = path.join(SRC, "probe/View.tsx");
  assert.ok(viewApiCalls(file, 'const V = () => { const api = useFooApi(); void api.list(); return <div />; };').length > 0);
  assert.ok(viewApiCalls(file, 'const V = () => { void useFooApi().list(); return <div />; };').length > 0);
  assert.deepEqual(viewApiCalls(file, 'const V = () => { const api = useFooApi(); const c = useCtl(api); return <div onClick={c.go} />; };'), []);
});
