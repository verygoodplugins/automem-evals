import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildChainAssociations,
  buildFactMemoryPayload,
  evaluateParameterGrounding,
  selectCases,
} from './lib.mjs';

test('buildFactMemoryPayload keeps benchmark source evidence in a scoped memory', () => {
  const payload = buildFactMemoryPayload({
    fact: {
      attribute: 'Wallet address',
      source_id: 'toolace_361',
      fact: 'The user stored wallet address 0xabc.',
      source_text: 'My wallet address is 0xabc.',
    },
    runTag: 'mem2actbench-run',
    qaId: 'qa_002',
    index: 0,
  });

  assert.match(payload.content, /0xabc/);
  assert.deepEqual(payload.tags, [
    'mem2actbench-run',
    'mem2actbench',
    'qa-qa_002',
  ]);
  assert.equal(payload.metadata.source_id, 'toolace_361');
});

test('buildChainAssociations links consecutive memories in temporal order', () => {
  assert.deepEqual(buildChainAssociations(['first', 'second', 'third']), [
    {
      memory1_id: 'first',
      memory2_id: 'second',
      type: 'RELATES_TO',
      strength: 0.8,
    },
    {
      memory1_id: 'second',
      memory2_id: 'third',
      type: 'RELATES_TO',
      strength: 0.8,
    },
  ]);
});

test('selectCases supports bounded resumable batches', () => {
  assert.deepEqual(selectCases(['a', 'b', 'c', 'd'], { offset: 1, limit: 2 }), [
    'b',
    'c',
  ]);
  assert.throws(() => selectCases([], { offset: -1 }), /non-negative/);
});

test('evaluateParameterGrounding scores sourced parameters and excludes defaults', () => {
  const qa = {
    qa_id: 'qa_001',
    evolution_chain: [
      {
        source_id: 'source_a',
        fact: 'User wants a seven day forecast for New York.',
        source_text: 'Could you check the upcoming week in New York?',
      },
      {
        source_id: 'source_b',
        fact: 'Unrelated weather preference.',
        source_text: 'I dislike rain.',
      },
    ],
    tool_call: {
      arguments: { location: 'New York', days: 7, units: 'metric' },
      grounding_info: {
        location: {
          type: 'explicit',
          source_text: 'Could you check the upcoming week in New York?',
        },
        days: {
          type: 'inferred',
          source_text: 'Could you check the upcoming week in New York?',
        },
        units: { type: 'default', source_text: 'default value' },
      },
    },
  };

  const result = evaluateParameterGrounding({
    qa,
    retrieved: [
      {
        memoryId: 'fact-1',
        content:
          'Fact: User wants a seven day forecast for New York. Source: Could you check the upcoming week in New York?',
      },
      { memoryId: 'fact-2', content: 'Fact: Unrelated weather preference.' },
    ],
  });

  assert.deepEqual(result, {
    supported: 2,
    expected: 2,
    falsePositiveEvidence: 1,
    defaultsExcluded: 1,
    unlabelledExcluded: 0,
    unsupportedParameters: [],
  });
});
