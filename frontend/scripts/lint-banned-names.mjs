#!/usr/bin/env node
/**
 * Banned-name lint for the Ultimate Trader frontend source.
 *
 * Mirrors the backend pytest in
 * `backend/tests/unit/lint/test_no_banned_product_names.py`.
 * Fails the build if any of the doctrine-banned phrases appears
 * in user-visible source under `src/` or `index.html`.
 *
 * Files allowed to mention these phrases (because the lint itself
 * defines them as data) are listed below.
 */
import { readdir, readFile, stat } from "node:fs/promises";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const ROOT = resolve(__dirname, "..");
const SCAN_PATHS = ["src", "index.html"];

// Phrases banned in active operator-facing source.
const BANNED_PHRASES = [
  "Account Governor",
  "Services Center",
  "Paper Runtime",
  "Live Runtime",
  "Deployment per Account",
  "Strategy Account",
  "Broker SubAccount",
  "Market Data Service Center",
  "Trading OS",
];

// Phrases banned as identifiers / brand strings in user-visible places.
const BANNED_NAV_LABELS = [
  // Top-nav must say "Accounts", never "Brokers", and never include
  // "Broker Runtime · Paper" / "Broker Runtime · Live".
  "Broker Runtime · Paper",
  "Broker Runtime · Live",
];

// Files this lint may mention banned names for self-documenting reasons.
const ALLOWED_FILES = new Set([
  // Lint script itself defines the banned set as data.
  relative(ROOT, __filename).replaceAll("\\", "/"),
]);

async function* walk(dir) {
  const entries = await readdir(dir, { withFileTypes: true });
  for (const entry of entries) {
    if (entry.name === "node_modules" || entry.name === "dist" || entry.name.startsWith(".")) continue;
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      yield* walk(path);
    } else if (
      entry.isFile() &&
      /\.(ts|tsx|js|jsx|html|css|md|mjs)$/.test(entry.name)
    ) {
      yield path;
    }
  }
}

const offenders = [];
const allBanned = [...BANNED_PHRASES, ...BANNED_NAV_LABELS];

async function isDir(p) {
  try {
    const s = await stat(p);
    return s.isDirectory();
  } catch {
    return false;
  }
}

async function isFile(p) {
  try {
    const s = await stat(p);
    return s.isFile();
  } catch {
    return false;
  }
}

async function scanFile(file) {
  const rel = relative(ROOT, file).replaceAll("\\", "/");
  if (ALLOWED_FILES.has(rel)) return;
  const text = await readFile(file, "utf8");
  for (const phrase of allBanned) {
    const idx = text.indexOf(phrase);
    if (idx !== -1) {
      const line = text.slice(0, idx).split("\n").length;
      offenders.push(`${rel}:${line} -- '${phrase}' is banned`);
    }
  }
}

for (const target of SCAN_PATHS) {
  const start = resolve(ROOT, target);
  if (await isDir(start)) {
    for await (const file of walk(start)) {
      await scanFile(file);
    }
  } else if (await isFile(start)) {
    await scanFile(start);
  }
}

if (offenders.length > 0) {
  console.error("Banned product-name phrases found in frontend source:");
  for (const o of offenders) console.error("  " + o);
  console.error("\nSee docs/architecture/NAMING_CONTRACT.md for the canonical names.");
  process.exit(1);
}

console.log("frontend banned-name lint: clean");
