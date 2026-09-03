/**
 * Find Probable Futures tilesets that no Mapbox style references (i.e. candidates for deletion).
 *
 * Mapbox has no reverse lookup from tileset to style, so this builds one: list every tileset in
 * the account, list every style, read each style's `sources`, and subtract.
 *
 * Draft styles are scanned by default. A tileset used only by a style's unpublished draft is still
 * in use, and skipping drafts would report it as unused — the one mistake that loses data here.
 *
 * Usage (from vector-tiles/, so .env with MAPBOX_ACCESS_TOKEN is picked up):
 *   npx ts-node scripts/tilesetUsage.ts                          # unused tilesets (the default)
 *   npx ts-node scripts/tilesetUsage.ts --index                  # full tileset -> styles index
 *   npx ts-node scripts/tilesetUsage.ts probablefutures.40101-east-v3   # check one tileset
 *   npx ts-node scripts/tilesetUsage.ts --no-drafts              # faster, but see the note above
 *   npx ts-node scripts/tilesetUsage.ts --out=/some/dir          # where the reports land
 *
 * Every full run writes TSV/TXT reports to vector-tiles/tileset-audit/ (see writeReport below).
 */
import mbxStyles from "@mapbox/mapbox-sdk/services/styles";
import mbxTilesets from "@mapbox/mapbox-sdk/services/tilesets";
import mbxClient from "@mapbox/mapbox-sdk/lib/client";
import { URL, URLSearchParams } from "url";
import * as fs from "fs";
import * as path from "path";

const env = require("dotenv").config();
if (env.error) {
  throw env.error;
}

const MAPBOX_USER = "probablefutures";
const baseClient = mbxClient({ accessToken: process.env["MAPBOX_ACCESS_TOKEN"] });
const stylesService = mbxStyles(baseClient);
const tilesetsService = mbxTilesets(baseClient);

const args = process.argv.slice(2);
const includeDrafts = !args.includes("--no-drafts");
const showIndex = args.includes("--index");
const target = args.find((arg) => !arg.startsWith("--"));
/** Every run writes its findings here, so the scan does not have to be repeated to act on it. */
const outDir =
  args.find((arg) => arg.startsWith("--out="))?.slice("--out=".length) ??
  path.join(__dirname, "..", "tileset-audit");

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** Mapbox rate-limits style reads hard, so back off and retry rather than losing a style. */
const withRetry = async <T>(label: string, run: () => Promise<T>, attempts = 9): Promise<T> => {
  for (let attempt = 1; ; attempt++) {
    try {
      return await run();
    } catch (error: any) {
      const retryable = error.statusCode === 429 || error.statusCode >= 500;
      if (!retryable || attempt === attempts) throw error;
      const wait = Math.min(30_000, 1000 * 2 ** (attempt - 1));
      console.error(`  … ${label}: ${error.message}, retrying in ${wait / 1000}s`);
      await sleep(wait);
    }
  }
};

type TilesetSummary = { id: string; name: string; modified: string; type: string };

const listTilesets = async (start?: string): Promise<TilesetSummary[]> => {
  const { body, links } = await withRetry<any>("listTilesets", () =>
    tilesetsService
      .listTilesets({ ownerId: MAPBOX_USER, limit: 500, start: start || undefined })
      .send(),
  );
  if (links.next?.url) {
    const searchParams = new URLSearchParams(new URL(links.next.url).search);
    return body.concat(await listTilesets(searchParams.get("start") ?? ""));
  }
  return body;
};

const listStyles = async (start?: string): Promise<any[]> => {
  const { body, links } = await withRetry<any>("listStyles", () =>
    stylesService.listStyles({ ownerId: MAPBOX_USER, start: start || undefined }).send(),
  );
  if (links.next?.url) {
    const searchParams = new URLSearchParams(new URL(links.next.url).search);
    return body.concat(await listStyles(searchParams.get("start") ?? ""));
  }
  return body;
};

const getStyle = async (styleId: string, draft = false) => {
  const request: any = { styleId };
  if (draft) request.draft = true;
  const { body } = await withRetry<any>(`${styleId}${draft ? " (draft)" : ""}`, () =>
    stylesService.getStyle(request).send(),
  );
  return body;
};

/** Tileset ids a style's sources point at, from every mapbox:// url (comma-joined ids included). */
const tilesetsOf = (style: any): string[] =>
  Object.values(style?.sources ?? {}).flatMap((source: any) => {
    const url: string | undefined = source?.url;
    if (!url?.startsWith("mapbox://")) return [];
    return url.replace("mapbox://", "").split(",");
  });

/** One style source pointing at one tileset. */
type Reference = { tilesetId: string; styleId: string; styleName: string; draft: boolean };

const label = (ref: Reference) =>
  `${ref.styleName} (${MAPBOX_USER}/${ref.styleId})${ref.draft ? " [draft]" : ""}`;

const writeReport = (name: string, lines: string[]) => {
  const file = path.join(outDir, name);
  fs.writeFileSync(file, lines.join("\n") + "\n");
  console.log(`  wrote ${file} (${lines.length} lines)`);
};

(async () => {
  const tilesets = await listTilesets();
  const styles = await listStyles();
  console.log(
    `${tilesets.length} tilesets, ${styles.length} styles in the ${MAPBOX_USER} account` +
      `${includeDrafts ? " (drafts included)" : " (drafts SKIPPED)"}\n`,
  );

  const references: Reference[] = [];
  const failures: string[] = [];

  for (const summary of styles) {
    for (const draft of includeDrafts ? [false, true] : [false]) {
      let style: any;
      try {
        style = await getStyle(summary.id, draft);
      } catch (error: any) {
        failures.push(`${MAPBOX_USER}/${summary.id}${draft ? " [draft]" : ""}\t${error.message}`);
        console.error(`  ! ${summary.id}${draft ? " (draft)" : ""}: ${error.message}`);
        continue;
      }
      await sleep(120); // pace the reads; the draft endpoint 429s in bursts otherwise
      for (const tilesetId of tilesetsOf(style)) {
        references.push({ tilesetId, styleId: summary.id, styleName: summary.name, draft });
      }
    }
  }

  const usage = new Map<string, Reference[]>();
  for (const ref of references) {
    if (!usage.has(ref.tilesetId)) usage.set(ref.tilesetId, []);
    usage.get(ref.tilesetId)!.push(ref);
  }

  if (failures.length) {
    console.error(
      `\n${failures.length} style read(s) failed — a tileset they use would look unused here. ` +
        `Re-run before deleting anything.\n`,
    );
  }

  if (target) {
    const users = usage.get(target) ?? [];
    if (!users.length) {
      console.log(`NOT USED: no style references ${target}.`);
      return;
    }
    console.log(`IN USE: ${target} is referenced by ${users.length} style(s):`);
    for (const ref of users) console.log(`  - ${label(ref)}`);
    return;
  }

  const unused = tilesets
    .filter((tileset) => !usage.has(tileset.id))
    .sort((a, b) => a.id.localeCompare(b.id));

  /** Styles whose sources point at an account tileset that no longer exists. */
  const brokenRefs = references.filter(
    (ref) =>
      ref.tilesetId.startsWith(`${MAPBOX_USER}.`) &&
      !tilesets.some((tileset) => tileset.id === ref.tilesetId),
  );

  if (showIndex) {
    for (const tilesetId of [...usage.keys()].sort()) {
      console.log(tilesetId);
      for (const ref of usage.get(tilesetId)!) console.log(`    ${label(ref)}`);
    }
  } else {
    console.log(`${unused.length} of ${tilesets.length} tilesets are referenced by no style:\n`);
    for (const tileset of unused) {
      console.log(`${tileset.id}\t${tileset.modified?.slice(0, 10)}\t${tileset.name}`);
    }
    if (brokenRefs.length) {
      console.log(`\n${brokenRefs.length} style source(s) point at tilesets that no longer exist.`);
    }
  }

  // Reports, so a scan this slow does not have to be repeated to act on it.
  fs.mkdirSync(outDir, { recursive: true });
  console.log(`\nReports (scan of ${new Date().toISOString()}):`);

  writeReport(
    "unused-tilesets.txt",
    unused.map((tileset) => tileset.id),
  );
  writeReport("unused-tilesets.tsv", [
    "tileset_id\tmodified\ttype\tname",
    ...unused.map((t) => `${t.id}\t${t.modified?.slice(0, 10)}\t${t.type}\t${t.name}`),
  ]);
  writeReport("broken-style-refs.tsv", [
    "style_id\tdraft\tmissing_tileset_id\tstyle_name",
    ...brokenRefs
      .map((ref) => `${ref.styleId}\t${ref.draft}\t${ref.tilesetId}\t${ref.styleName}`)
      .sort(),
  ]);
  writeReport(
    "broken-style-ids.txt",
    [...new Set(brokenRefs.map((ref) => ref.styleId))].sort(),
  );
  writeReport("tileset-style-index.tsv", [
    "tileset_id\tstyle_id\tdraft\tstyle_name",
    ...references
      .map((ref) => `${ref.tilesetId}\t${ref.styleId}\t${ref.draft}\t${ref.styleName}`)
      .sort(),
  ]);
  writeReport("scan-failures.tsv", ["style\terror", ...failures]);
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
