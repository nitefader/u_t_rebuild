import { readdir, readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { join } from "node:path";

const root = fileURLToPath(new URL("..", import.meta.url));
const forbiddenImportPattern = /from\s+["'][^"']*(backend|brokers?|alpaca|orderManager|OrderManager|brokerSync|BrokerSync|featureEngine|FeatureEngine|signalEngine|SignalEngine)[^"']*["']/;

async function collectFiles(dir) {
  const entries = await readdir(dir, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (["dist", "node_modules"].includes(entry.name)) {
        continue;
      }
      files.push(...await collectFiles(path));
    } else if (/\.(js|mjs|html|css)$/.test(entry.name)) {
      files.push(path);
    }
  }
  return files;
}

const files = await collectFiles(root);
const sourceFiles = files.filter((file) => !file.includes(`${join("frontend", "tests")}`));

for (const file of sourceFiles) {
  const source = await readFile(file, "utf8");
  if (forbiddenImportPattern.test(source)) {
    throw new Error(`Forbidden runtime/internal import found in ${file}`);
  }
}

await import("../src/api/operations.js");
await import("../src/api/services.js");
await import("../src/operationsCenter.js");
await import("../src/servicesCenter.js");

console.log(`Frontend check passed for ${sourceFiles.length} files.`);
