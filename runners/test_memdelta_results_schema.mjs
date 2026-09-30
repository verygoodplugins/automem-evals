import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const schemaPath = path.join(
  repoRoot,
  'docs',
  'protocols',
  'memdelta-controlled-results.schema.json'
);

test('MemDelta result schema requires model and write-path disclosures', () => {
  const schema = JSON.parse(fs.readFileSync(schemaPath, 'utf8'));
  const controlled = schema.$defs.controlled_evaluation;

  assert.equal(schema.$id, 'https://verygoodplugins.com/schemas/automem-evals/memdelta-controlled-results.v1.json');
  assert.equal(schema.$ref, '#/$defs/controlled_evaluation');
  assert.deepEqual(controlled.required, [
    'embedding_model',
    'reader_model',
    'judge',
    'graph',
    'recall',
    'write_path_cost',
  ]);
  assert.deepEqual(controlled.properties.write_path_cost.required, [
    'input_tokens',
    'latency_ms',
    'enrichment_calls',
  ]);
  assert.deepEqual(controlled.properties.graph.required, ['edges']);
  assert.deepEqual(controlled.properties.recall.required, ['relation_expansion']);
});

test('judged BEAM artifacts carry the controlled-evaluation metadata block', () => {
  const runner = fs.readFileSync(
    path.join(repoRoot, 'runners', 'beam_judged_eval.py'),
    'utf8'
  );

  for (const field of [
    'controlled_evaluation',
    'embedding_model',
    'reader_model',
    'write_path_cost',
  ]) {
    assert.match(runner, new RegExp(`['\"]${field}['\"]`));
  }
});
