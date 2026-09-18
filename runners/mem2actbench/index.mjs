#!/usr/bin/env node
/**
 * Mem2ActBench AutoMem parameter-grounding pilot.
 *
 * Usage (from the repo root):
 *   node runners/mem2actbench/index.mjs \
 *     --dataset data/benchmarks/mem2actbench/toolmembench_small/qa_dataset.jsonl
 *
 * This is a retrieval-evidence evaluation, deliberately separated from LLM
 * tool-call generation. See runners/mem2actbench/README.md.
 */

import { randomUUID } from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

import {
  buildChainAssociations,
  buildFactMemoryPayload,
  evaluateParameterGrounding,
  selectCases,
} from './lib.mjs';

// Defaults are repo-relative. The dataset clone and raw per-run reports are
// both gitignored; curated aggregates live under data/results/mem2actbench/.
const REPO_ROOT = fileURLToPath(new URL('../../', import.meta.url));
const DEFAULT_DATASET =
  'data/benchmarks/mem2actbench/toolmembench_small/qa_dataset.jsonl';
const DEFAULT_OUTPUT = 'data/results/mem2actbench/runs';

// Reports record the dataset without the local filesystem prefix.
function displayPath(filePath) {
  const relative = path.relative(REPO_ROOT, filePath);
  return relative && !relative.startsWith('..') && !path.isAbsolute(relative)
    ? relative
    : path.join(path.basename(path.dirname(filePath)), path.basename(filePath));
}

function parseArgs(argv = process.argv.slice(2)) {
  const options = {
    dataset: path.join(REPO_ROOT, DEFAULT_DATASET),
    output: path.join(REPO_ROOT, DEFAULT_OUTPUT),
    limit: null,
    offset: 0,
    recallK: 5,
    keep: false,
    dryRun: false,
    runId: `mem2actbench-${randomUUID().slice(0, 8)}`,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === '--dataset') {
      options.dataset = argv[(index += 1)];
    } else if (arg === '--output') {
      options.output = argv[(index += 1)];
    } else if (arg === '--limit') {
      options.limit = Number(argv[(index += 1)]);
    } else if (arg === '--offset') {
      options.offset = Number(argv[(index += 1)]);
    } else if (arg === '--recall-k') {
      options.recallK = Number(argv[(index += 1)]);
    } else if (arg === '--keep') {
      options.keep = true;
    } else if (arg === '--dry-run') {
      options.dryRun = true;
    } else if (arg === '--run-id') {
      options.runId = argv[(index += 1)];
    } else if (arg === '--help' || arg === '-h') {
      options.help = true;
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }
  if (!Number.isInteger(options.recallK) || options.recallK < 1) {
    throw new Error('--recall-k must be a positive integer.');
  }
  if (
    options.limit !== null &&
    (!Number.isInteger(options.limit) || options.limit < 1)
  ) {
    throw new Error('--limit must be a positive integer.');
  }
  if (!Number.isInteger(options.offset) || options.offset < 0) {
    throw new Error('--offset must be a non-negative integer.');
  }
  return options;
}

async function readJsonl(filePath) {
  const raw = await fs.readFile(filePath, 'utf8');
  return raw
    .split('\n')
    .filter(Boolean)
    .map((line, index) => {
      try {
        return JSON.parse(line);
      } catch (error) {
        throw new Error(
          `Invalid JSON on dataset line ${index + 1}: ${error.message}`
        );
      }
    });
}

function automemConfig(env = process.env) {
  const endpoint = env.AUTOMEM_API_URL || env.AUTOMEM_ENDPOINT;
  const token = env.AUTOMEM_API_KEY || env.AUTOMEM_API_TOKEN;
  if (!endpoint || !token) {
    throw new Error(
      'AUTOMEM_API_URL and AUTOMEM_API_KEY are required (deprecated AUTOMEM_ENDPOINT and AUTOMEM_API_TOKEN also work).'
    );
  }
  return { endpoint: endpoint.replace(/\/$/, ''), token };
}

function headers(config) {
  return {
    Authorization: `Bearer ${config.token}`,
    'Content-Type': 'application/json',
  };
}

async function request(config, requestPath, options = {}) {
  const response = await fetch(`${config.endpoint}${requestPath}`, {
    ...options,
    headers: { ...headers(config), ...(options.headers || {}) },
  });
  if (!response.ok) {
    throw new Error(
      `${options.method || 'GET'} ${requestPath} failed: ${response.status} ${await response.text()}`
    );
  }
  return response.status === 204 ? null : response.json();
}

async function storeMemory(config, payload) {
  const result = await request(config, '/memory', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  const memoryId = result.memory_id || result.id;
  if (!memoryId) {
    throw new Error('AutoMem store response did not contain a memory id.');
  }
  return memoryId;
}

async function recallMemories(config, query, tag, limit) {
  const params = new URLSearchParams({
    query,
    tags: tag,
    limit: String(limit),
  });
  const result = await request(config, `/recall?${params}`);
  return (result.results || [])
    .map(item => ({
      memoryId: item.memory_id || item.memory?.id || item.id || null,
      content:
        item.memory?.content || item.memory?.summary || item.content || '',
    }))
    .filter(item => item.content);
}

async function deleteMemory(config, memoryId) {
  try {
    await request(config, `/memory/${encodeURIComponent(memoryId)}`, {
      method: 'DELETE',
    });
    return null;
  } catch (error) {
    return error.message;
  }
}

function percentage(numerator, denominator) {
  return denominator === 0
    ? 0
    : Number(((numerator / denominator) * 100).toFixed(2));
}

function summaryFromCases(cases, options) {
  const totals = cases.reduce(
    (summary, item) => {
      summary.supported += item.score.supported;
      summary.expected += item.score.expected;
      summary.falsePositiveEvidence += item.score.falsePositiveEvidence;
      summary.defaultsExcluded += item.score.defaultsExcluded;
      summary.unlabelledExcluded += item.score.unlabelledExcluded;
      summary.strictTasks +=
        item.score.supported === item.score.expected ? 1 : 0;
      return summary;
    },
    {
      supported: 0,
      expected: 0,
      falsePositiveEvidence: 0,
      defaultsExcluded: 0,
      unlabelledExcluded: 0,
      strictTasks: 0,
    }
  );
  const falseNegatives = totals.expected - totals.supported;
  const precision =
    totals.supported + totals.falsePositiveEvidence === 0
      ? 0
      : totals.supported / (totals.supported + totals.falsePositiveEvidence);
  const recall = totals.expected === 0 ? 0 : totals.supported / totals.expected;
  const f1 =
    precision + recall === 0
      ? 0
      : (2 * precision * recall) / (precision + recall);
  return {
    benchmark: 'Mem2ActBench',
    run_id: options.runId,
    dataset: options.dataset,
    tasks: cases.length,
    recall_k: options.recallK,
    scoring: {
      definition:
        'A non-default labelled tool parameter is supported when a recalled fact contains its labelled source text or fact. Extra recalled facts that support no labelled parameter are false-positive evidence.',
      supported_parameters: totals.supported,
      expected_parameters: totals.expected,
      false_positive_evidence: totals.falsePositiveEvidence,
      false_negative_parameters: falseNegatives,
      defaults_excluded: totals.defaultsExcluded,
      unlabelled_parameters_excluded: totals.unlabelledExcluded,
      parameter_accuracy_percent: percentage(totals.supported, totals.expected),
      precision_percent: Number((precision * 100).toFixed(2)),
      recall_percent: Number((recall * 100).toFixed(2)),
      f1_percent: Number((f1 * 100).toFixed(2)),
      strict_task_accuracy_percent: percentage(
        totals.strictTasks,
        cases.length
      ),
    },
  };
}

async function runCase(config, qa, options) {
  const storedIds = [];
  let associationFailures = 0;
  try {
    for (const [index, fact] of (qa.evolution_chain || []).entries()) {
      const memoryId = await storeMemory(
        config,
        buildFactMemoryPayload({
          fact,
          runTag: options.runId,
          qaId: qa.qa_id,
          index,
        })
      );
      storedIds.push(memoryId);
    }
    for (const association of buildChainAssociations(storedIds)) {
      try {
        await request(config, '/associate', {
          method: 'POST',
          body: JSON.stringify(association),
        });
      } catch {
        associationFailures += 1;
      }
    }
    const retrieved = await recallMemories(
      config,
      qa.query,
      options.runId,
      options.recallK
    );
    return {
      qa_id: qa.qa_id,
      tool_name: qa.tool_call?.name || null,
      complexity: qa.complexity_metadata?.level || null,
      retrieved_evidence: retrieved.length,
      association_failures: associationFailures,
      score: evaluateParameterGrounding({ qa, retrieved }),
    };
  } finally {
    if (!options.keep) {
      await Promise.all(
        storedIds.map(memoryId => deleteMemory(config, memoryId))
      );
    }
  }
}

function printHelp() {
  console.log(`Usage: node runners/mem2actbench/index.mjs [options]

  --dataset PATH     QA JSONL (default: ${DEFAULT_DATASET})
  --output DIR       Results directory (default: ${DEFAULT_OUTPUT})
  --offset N         Skip first N QA tasks (default: 0)
  --limit N          Run N QA tasks starting at --offset
  --recall-k N       Number of recalled facts per task (default: 5)
  --keep             Keep run-scoped AutoMem facts instead of cleanup
  --dry-run          Parse and summarize dataset without calling AutoMem
  --run-id ID        Stable run tag (default: generated UUID suffix)`);
}

async function main() {
  const options = parseArgs();
  if (options.help) {
    return printHelp();
  }
  const datasetPath = path.resolve(options.dataset);
  const allCases = await readJsonl(datasetPath);
  const cases = selectCases(allCases, options);
  options.dataset = displayPath(datasetPath);
  if (options.dryRun) {
    console.log(
      JSON.stringify(
        {
          benchmark: 'Mem2ActBench',
          dataset: options.dataset,
          available_tasks: allCases.length,
          offset: options.offset,
          selected_tasks: cases.length,
          dry_run: true,
        },
        null,
        2
      )
    );
    return;
  }

  const config = automemConfig();
  const results = [];
  for (const [index, qa] of cases.entries()) {
    const result = await runCase(config, qa, options);
    results.push(result);
    console.error(`Completed ${index + 1}/${cases.length}: ${qa.qa_id}`);
  }
  const report = {
    ...summaryFromCases(results, options),
    completed_at: new Date().toISOString(),
    cleanup: options.keep ? 'retained' : 'deleted after each task',
    cases: results,
  };
  await fs.mkdir(options.output, { recursive: true });
  const outputPath = path.join(options.output, `${options.runId}.json`);
  await fs.writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`);
  console.log(
    JSON.stringify({ ...report, cases: undefined, output: outputPath }, null, 2)
  );
}

main().catch(error => {
  console.error(`mem2actbench pilot failed: ${error.message}`);
  process.exitCode = 1;
});
