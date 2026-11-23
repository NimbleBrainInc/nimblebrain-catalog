#!/usr/bin/env node
// Checks AI Catalog documents against the AI Catalog spec, using Vercel's
// TypeScript SDK for it (vercel-labs/ai-catalog-sdk).
//
//   node scripts/check-ai-catalog.mjs <catalog.json>...
//
// The SDK is built from a pinned commit of its repo, since a release reaches its
// GitHub tag before npm. To move to a newer spec, set SDK_COMMIT to the commit of
// the SDK release that implements it; `specVersion` is then checked against that
// release's spec version. The build is cached in the OS temp directory, keyed by
// the commit.
//
// A document passes when:
// - the SDK parses it and its authoring validation (`assertValidCatalog`) passes;
// - its `specVersion` is the spec version the SDK implements, which the SDK's
//   validation does not check, and the spec requires a producer to state;
// - every `urn:air` identifier ends in the kind its `type` names (`:mcp`,
//   `:plugin`, `:catalog`, `:skill`). The spec reads `urn:air:{publisher}:{name}:{kind}`
//   and leaves kinds to the publisher; this vocabulary is ours. A consumer that
//   derives a display name from the identifier shows `{name}`, so a kind in the
//   name segment is what it would show.
//
// This file is the same in every repo that publishes an AI Catalog. Change it in
// all of them.

import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const SDK_REPO = "https://github.com/vercel-labs/ai-catalog-sdk.git";
const SDK_COMMIT = "1fd9de447b612387e8b7955110614de213fc6ddb"; // v0.1.0, spec 0.9
const PNPM = "pnpm@11.1.3"; // the SDK's `packageManager`

const KIND_BY_TYPE = {
  "application/mcp-server-card+json": "mcp",
  "application/agent-plugins+zip": "plugin",
  "application/agent-plugins+gzip": "plugin",
  "application/ai-catalog+json": "catalog",
  "application/agent-skills+zip": "skill",
  "application/agent-skills+gzip": "skill",
  "application/agent-skills+json": "skill",
  "application/agent-skills+md": "skill",
};

function sdkDir() {
  const dir = join(tmpdir(), `ai-catalog-sdk-${SDK_COMMIT}`);
  const done = join(dir, ".built");
  if (existsSync(done)) return dir;
  rmSync(dir, { recursive: true, force: true });
  mkdirSync(dir, { recursive: true });
  const run = (cmd, args) => execFileSync(cmd, args, { cwd: dir, stdio: ["ignore", "ignore", "inherit"] });
  run("git", ["init", "--quiet"]);
  run("git", ["fetch", "--quiet", "--depth", "1", SDK_REPO, SDK_COMMIT]);
  run("git", ["checkout", "--quiet", "FETCH_HEAD"]);
  run("npx", ["--yes", PNPM, "install", "--frozen-lockfile", "--silent"]);
  run("npx", ["--yes", PNPM, "run", "--silent", "build"]);
  writeFileSync(done, "");
  return dir;
}

function issues(error) {
  return (error.issues ?? [{ message: error.message }]).map(
    (i) => `${(i.path ?? []).join(".") || "(document)"}: ${i.message}`,
  );
}

const files = process.argv.slice(2);
if (files.length === 0) {
  console.error("usage: check-ai-catalog.mjs <catalog.json>...");
  process.exit(2);
}

const sdk = await import(pathToFileURL(join(sdkDir(), "dist", "index.js")).href);
const specVersion = sdk.implementedSpecRevision.specVersion;
let failed = false;

for (const file of files) {
  const problems = [];
  let catalog;
  try {
    catalog = sdk.parseCatalogJson(readFileSync(file, "utf8"));
    sdk.assertValidCatalog(catalog);
  } catch (error) {
    problems.push(...issues(error));
  }
  if (catalog) {
    if (catalog.specVersion !== specVersion) {
      problems.push(`specVersion: is "${catalog.specVersion}", this SDK implements "${specVersion}"`);
    }
    catalog.entries.forEach((entry, i) => {
      const kind = KIND_BY_TYPE[entry.type];
      if (!kind || !entry.identifier.startsWith("urn:air:")) return;
      if (!entry.identifier.endsWith(`:${kind}`) || entry.identifier.split(":").length !== 5) {
        problems.push(
          `entries.${i}.identifier: "${entry.identifier}" should read urn:air:{publisher}:{name}:${kind}`,
        );
      }
    });
  }
  if (problems.length > 0) {
    failed = true;
    console.error(`✗ ${file}`);
    for (const p of problems) console.error(`  ${p}`);
  } else {
    console.log(`✓ ${file} (AI Catalog ${specVersion}, ${catalog.entries.length} entries)`);
  }
}

process.exit(failed ? 1 : 0);
