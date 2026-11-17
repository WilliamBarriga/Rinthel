import { mkdtempSync, readFileSync, readdirSync, rmSync, symlinkSync, writeFileSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test, { after } from "node:test";
import assert from "node:assert/strict";
import { InMemoryInstanceSoul } from "../dist/instance-soul.js";
import { FsInstanceSoul } from "../dist/instance-soul-fs.js";
import { instanceSoulContract } from "./contract/instance-soul.mjs";

const dir = mkdtempSync(path.join(tmpdir(), "deck-soul-"));
after(() => rmSync(dir, { recursive: true, force: true }));
let n = 0;

instanceSoulContract("in-memory", async () => new InMemoryInstanceSoul());
instanceSoulContract("filesystem", async () => new FsInstanceSoul(path.join(dir, `case-${n++}`, "instance", "SOUL.md")));

test("filesystem instance soul: reads what INSTALL seeded, and writes beside it without leaving temporaries", () => {
  const file = path.join(dir, "seeded", "instance", "SOUL.md");
  mkdirSync(path.dirname(file), { recursive: true });
  writeFileSync(file, "# seeded\n");
  const soul = new FsInstanceSoul(file);
  assert.equal(soul.read(), "# seeded\n");
  soul.write("# edited");
  assert.equal(readFileSync(file, "utf8"), "# edited\n");
  assert.deepEqual(readdirSync(path.dirname(file)), ["SOUL.md"]);
});

test("filesystem instance soul: a SOUL.md that is a link is neither read nor written through", () => {
  const folder = path.join(dir, "linked");
  mkdirSync(folder, { recursive: true });
  const target = path.join(folder, "secret.txt");
  writeFileSync(target, "nope\n");
  const file = path.join(folder, "SOUL.md");
  symlinkSync(target, file);
  const soul = new FsInstanceSoul(file);
  assert.equal(soul.read(), null);
  soul.write("mine");
  assert.equal(readFileSync(target, "utf8"), "nope\n");
  assert.equal(soul.read(), "mine\n");
});
