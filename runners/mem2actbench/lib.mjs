/**
 * Pure helpers for the Mem2ActBench AutoMem pilot.
 *
 * The benchmark's labels say which historical text grounds each parameter but
 * do not supply a generated tool call. This pilot therefore scores retrieval
 * evidence, not an LLM's argument synthesis: a parameter is supported when a
 * recalled memory contains its labelled source text or labelled fact.
 */

function normalizeText(value) {
  return String(value || '')
    .toLocaleLowerCase('en-US')
    .replace(/\s+/g, ' ')
    .trim();
}

function evidencePresent(content, candidates) {
  const normalizedContent = normalizeText(content);
  return candidates.some(candidate => {
    const normalizedCandidate = normalizeText(candidate);
    return (
      normalizedCandidate && normalizedContent.includes(normalizedCandidate)
    );
  });
}

export function buildFactMemoryPayload({ fact, runTag, qaId, index }) {
  const content = [
    `Mem2ActBench fact ${index + 1} for ${qaId}.`,
    `Attribute: ${fact.attribute || 'Unspecified'}.`,
    `Fact: ${fact.fact || 'Unspecified'}`,
    `Source text: ${fact.source_text || 'Unspecified'}`,
  ].join('\n');

  return {
    content,
    type: 'Context',
    tags: [runTag, 'mem2actbench', `qa-${qaId}`],
    importance: 0.7,
    confidence: 0.9,
    metadata: {
      benchmark: 'Mem2ActBench',
      qa_id: qaId,
      source_id: fact.source_id || null,
      chain_index: index,
    },
  };
}

export function buildChainAssociations(memoryIds) {
  return memoryIds.slice(1).map((memory2Id, index) => ({
    memory1_id: memoryIds[index],
    memory2_id: memory2Id,
    type: 'RELATES_TO',
    strength: 0.8,
  }));
}

export function selectCases(cases, { offset = 0, limit = null } = {}) {
  if (!Number.isInteger(offset) || offset < 0) {
    throw new Error('offset must be a non-negative integer.');
  }
  if (limit !== null && (!Number.isInteger(limit) || limit < 1)) {
    throw new Error('limit must be a positive integer when set.');
  }
  return cases.slice(offset, limit === null ? undefined : offset + limit);
}

export function evaluateParameterGrounding({ qa, retrieved }) {
  const chain = Array.isArray(qa.evolution_chain) ? qa.evolution_chain : [];
  const groundingInfo = qa.tool_call?.grounding_info || {};
  const argumentNames = Object.keys(qa.tool_call?.arguments || {});
  const evaluable = [];
  let defaultsExcluded = 0;
  let unlabelledExcluded = 0;

  for (const name of argumentNames) {
    const label = groundingInfo[name];
    if (!label) {
      unlabelledExcluded += 1;
      continue;
    }
    if (label.type === 'default') {
      defaultsExcluded += 1;
      continue;
    }
    const matchingFacts = chain.filter(
      fact =>
        normalizeText(fact.source_text) === normalizeText(label.source_text) ||
        normalizeText(fact.fact) === normalizeText(label.source_text)
    );
    evaluable.push({
      name,
      value: qa.tool_call.arguments[name],
      sourceText: label.source_text,
      candidates: [
        label.source_text,
        ...matchingFacts.flatMap(fact => [fact.fact, fact.source_text]),
      ],
    });
  }

  const supportedParameters = evaluable.filter(parameter =>
    retrieved.some(result =>
      evidencePresent(result.content, parameter.candidates)
    )
  );
  const supportedEvidence = new Set();
  for (const result of retrieved) {
    if (
      evaluable.some(parameter =>
        evidencePresent(result.content, parameter.candidates)
      )
    ) {
      supportedEvidence.add(result.memoryId || result.content);
    }
  }

  return {
    supported: supportedParameters.length,
    expected: evaluable.length,
    falsePositiveEvidence: Math.max(
      0,
      retrieved.length - supportedEvidence.size
    ),
    defaultsExcluded,
    unlabelledExcluded,
    unsupportedParameters: evaluable
      .filter(parameter => !supportedParameters.includes(parameter))
      .map(parameter => ({ name: parameter.name, value: parameter.value })),
  };
}
