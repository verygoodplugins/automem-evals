/**
 * Drive WRIT against AutoMem. Lives in writ/ at run time (driver copies it in).
 *
 * Reuses writ's exported runBenchmark + scenario loaders so we never patch
 * cli.ts. Output format matches cli.ts so the Python driver parses both runs
 * with the same code.
 */

import { parseArgs } from "node:util";
import { writeFile, mkdir } from "node:fs/promises";
import { join } from "node:path";
import { loadAllScenarios, loadScenariosByCategory } from "./src/loader.js";
import { runBenchmark, WRIT_VERSION } from "./src/runner.js";
import { generateMarkdownReport } from "./src/report.js";
import { AutoMemAdapter } from "./src/adapters/automem.js";
import type { ScenarioCategory, EvaluationMode } from "./src/types.js";

const { values } = parseArgs({
  options: {
    scenarios: { type: "string", default: "all" },
    modes: { type: "string", default: "native_memory" },
    endpoint: { type: "string", default: "http://localhost:8001" },
    token: { type: "string", default: "test-token" },
    output: { type: "string", default: "results" },
    "output-format": { type: "string", default: "both" },
  },
  strict: false,
});

async function main() {
  const scenarioFilter = String(values.scenarios ?? "all");
  const modesStr = String(values.modes ?? "native_memory");
  const endpoint = String(values.endpoint ?? "http://localhost:8001");
  const token = String(values.token ?? "test-token");
  const outputDir = String(values.output ?? "results");
  const outputFormat = String(values["output-format"] ?? "both");

  const adapter = new AutoMemAdapter({ endpoint, token });
  const modes = modesStr
    .split(",")
    .map((mode) => mode.trim())
    .filter(Boolean) as EvaluationMode[];

  console.log(`WRIT Benchmark v${WRIT_VERSION}`);
  console.log(`Adapter: ${adapter.name}`);
  console.log(`Endpoint: ${endpoint}`);
  console.log(`Modes: ${modes.join(", ")}`);
  console.log(`Scenarios: ${scenarioFilter}`);
  console.log("---");

  const scenarios =
    scenarioFilter === "all"
      ? await loadAllScenarios()
      : await loadScenariosByCategory(scenarioFilter as ScenarioCategory);

  if (scenarios.length === 0) {
    console.log("No scenarios found.");
    process.exit(1);
  }

  console.log(`Loaded ${scenarios.length} scenarios\n`);

  const report = await runBenchmark({
    scenarios,
    adapter,
    modes,
    onScenarioComplete: (result) => {
      const status = result.detected_failures.length === 0 ? "PASS" : "FAIL";
      const failures = result.detected_failures.join(", ") || "none";
      console.log(
        `  [${status}] ${result.scenario_id} (${result.mode}) — failures: ${failures}`
      );
    },
  });

  console.log("\n--- Aggregate Scores ---");
  console.log(`Recall Accuracy:         ${pct(report.aggregate.recall_accuracy)}`);
  console.log(`Update Fidelity:         ${pct(report.aggregate.update_fidelity)}`);
  console.log(`Drift Rate:              ${pct(report.aggregate.drift_rate)}`);
  console.log(`Detectability:           ${pct(report.aggregate.detectability)}`);
  console.log(`Temporal Accuracy:       ${pct(report.aggregate.temporal_accuracy)}`);
  console.log(`Provenance Completeness: ${pct(report.aggregate.provenance_completeness)}`);
  console.log(`Constraint Consistency:  ${pct(report.aggregate.constraint_consistency)}`);
  console.log(`Hallucination Rate:      ${pct(report.aggregate.hallucination_rate)}`);
  console.log(`Abstention Quality:      ${pct(report.aggregate.abstention_quality)}`);

  await mkdir(outputDir, { recursive: true });
  const baseName = `writ-${adapter.name}-${Date.now()}`;

  if (outputFormat === "json" || outputFormat === "both") {
    const jsonPath = join(outputDir, `${baseName}.json`);
    await writeFile(jsonPath, JSON.stringify(report, null, 2));
    console.log(`\nJSON report: ${jsonPath}`);
  }

  if (outputFormat === "markdown" || outputFormat === "both") {
    const md = await generateMarkdownReport(report);
    const mdPath = join(outputDir, `${baseName}.md`);
    await writeFile(mdPath, md);
    console.log(`Markdown report: ${mdPath}`);
  }
}

function pct(n: number): string {
  return `${(n * 100).toFixed(1)}%`;
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
