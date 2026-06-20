/**
 * check-api-types-fresh.mjs — drift detection para tipos auto-generados.
 *
 * CI corre este script. Si los tipos commiteados (src/api/generated.ts +
 * src/api/openapi.json) no coinciden con lo que `gen:api` produciría
 * AHORA contra el código actual del backend, sale con exit code 1 y
 * muestra qué archivo está stale.
 *
 * Esto evita que un cambio de schema en backend se mergee sin que el
 * frontend regenere sus tipos — la rama queda en rojo hasta que el
 * autor del PR corra `npm run gen:api` y commitee los cambios.
 *
 * Asume cwd = web/ (npm script lo invoca desde ahí).
 */

import { execSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, copyFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const REPO_ROOT = join(process.cwd(), "..");
const COMMITTED_JSON = join(process.cwd(), "src/api/openapi.json");
const COMMITTED_TS = join(process.cwd(), "src/api/generated.ts");

function run(cmd, opts = {}) {
  return execSync(cmd, { stdio: "pipe", ...opts }).toString();
}

function fail(msg) {
  console.error(`\n❌  ${msg}\n`);
  console.error("Cómo arreglarlo: desde web/ ejecutá `npm run gen:api` y commiteá los cambios.");
  process.exit(1);
}

if (!existsSync(COMMITTED_JSON) || !existsSync(COMMITTED_TS)) {
  fail("Faltan los tipos generados (src/api/openapi.json o generated.ts). Corré `npm run gen:api`.");
}

const tmp = mkdtempSync(join(tmpdir(), "orion-api-check-"));
const tmpJson = join(tmp, "openapi.json");
const tmpTs = join(tmp, "generated.ts");

try {
  // Backup actual, regenerar a tmp, comparar bytes, restaurar.
  // Hacemos esto en lugar de generar en tmp directamente para evitar
  // que el script Python tenga que aceptar un parámetro de output path.
  copyFileSync(COMMITTED_JSON, tmpJson);
  copyFileSync(COMMITTED_TS, tmpTs);

  run("python ../scripts/dump_openapi.py", { cwd: process.cwd() });
  run("npx openapi-typescript src/api/openapi.json -o src/api/generated.ts");
  run('npx prettier --write src/api/generated.ts --log-level error');

  const newJson = readFileSync(COMMITTED_JSON, "utf-8");
  const newTs = readFileSync(COMMITTED_TS, "utf-8");
  const oldJson = readFileSync(tmpJson, "utf-8");
  const oldTs = readFileSync(tmpTs, "utf-8");

  const jsonDrift = newJson !== oldJson;
  const tsDrift = newTs !== oldTs;

  // Restauramos lo committed antes de tirar error.
  copyFileSync(tmpJson, COMMITTED_JSON);
  copyFileSync(tmpTs, COMMITTED_TS);

  if (jsonDrift || tsDrift) {
    const files = [jsonDrift && "openapi.json", tsDrift && "generated.ts"]
      .filter(Boolean)
      .join(" + ");

    // Mostrar las primeras N líneas distintas para que el log de CI
    // diga EXACTAMENTE qué cambió — la primera vez que esto fallaba,
    // el mensaje genérico "stale" no decía si era LF/CRLF, sort order,
    // versión de openapi-typescript, etc.
    const dumpDiff = (label, oldStr, newStr) => {
      const oldLines = oldStr.split("\n");
      const newLines = newStr.split("\n");
      console.error(`\n--- ${label} (- committed / + regenerated) ---`);
      const max = Math.max(oldLines.length, newLines.length);
      let shown = 0;
      for (let i = 0; i < max && shown < 20; i++) {
        if (oldLines[i] !== newLines[i]) {
          console.error(`  L${i + 1}-: ${JSON.stringify(oldLines[i] ?? "")}`);
          console.error(`  L${i + 1}+: ${JSON.stringify(newLines[i] ?? "")}`);
          shown++;
        }
      }
      if (shown === 20) console.error("  ... (truncado a 20 diffs)");
    };
    if (jsonDrift) dumpDiff("openapi.json", oldJson, newJson);
    if (tsDrift) dumpDiff("generated.ts", oldTs, newTs);

    fail(`Tipos API stale — el backend cambió y ${files} no se regeneraron.`);
  }

  console.log("✓ API types están al día con el OpenAPI del backend");
} finally {
  try {
    rmSync(tmp, { recursive: true, force: true });
  } catch {
    /* ignore tmp cleanup errors */
  }
}
