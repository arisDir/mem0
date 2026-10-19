// TypeScript client smoke test against the self-hosted platform-compat layer.
// The mem0-ts package must be built first: `cd mem0-ts && npm install && npx tsup`.
// Run: MEM0_API_KEY=m0sk_... MEM0_API_URL=http://localhost:8888 \
//        node server/scripts/verify_platform_compat_ts.cjs
const crypto = require("node:crypto");
const path = require("node:path");

// Resolve the built TypeScript client: override with MEM0_TS_DIST if needed.
const distPath =
  process.env.MEM0_TS_DIST || path.resolve(__dirname, "../../mem0-ts/dist/index.js");
const { MemoryClient } = require(distPath);

const API_URL = (process.env.MEM0_API_URL || "http://localhost:8888").replace(/\/$/, "");
const API_KEY = process.env.MEM0_API_KEY;
if (!API_KEY) {
  console.error("MEM0_API_KEY is required");
  process.exit(2);
}

const UID = "ts-compat-smoke-" + crypto.randomBytes(4).toString("hex");
let failures = 0;

function check(name, ok, detail) {
  console.log(`  [${ok ? "PASS" : "FAIL"}] ${name}${ok || !detail ? "" : " — " + detail}`);
  if (!ok) failures++;
}

async function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function main() {
  console.log(`Verifying TypeScript MemoryClient against ${API_URL}`);
  const c = new MemoryClient({ apiKey: API_KEY, host: API_URL });

  await c.add([{ role: "user", content: "I prefer aisle seats" }], { user_id: UID });

  let hits = [];
  for (let i = 0; i < 15; i++) {
    const res = await c.search("seat preference", { filters: { user_id: UID } });
    hits = res.results || res;
    if (Array.isArray(hits) && hits.some((h) => (h.memory || "").includes("aisle"))) break;
    await sleep(2000);
  }
  check(
    "ts: search finds added memory",
    Array.isArray(hits) && hits.some((h) => (h.memory || "").includes("aisle")),
    JSON.stringify(hits),
  );

  const listed = await c.getAll({ filters: { user_id: UID } });
  const results = listed.results || listed;
  check("ts: getAll returns results", Array.isArray(results) && results.length > 0, JSON.stringify(listed));

  if (Array.isArray(results) && results.length > 0) {
    const id = results[0].id;
    const got = await c.get(id);
    check("ts: get by id", !!got, JSON.stringify(got));
  }

  await c.deleteAll({ user_id: UID });
  check("ts: deleteAll", true);

  if (failures) {
    console.error(`\n${failures} check(s) failed`);
    process.exit(1);
  }
  console.log("\nAll checks passed.");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
