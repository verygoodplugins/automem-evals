import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import test from 'node:test';

import { createAmlAdapterServer, recallParams } from './adapter.mjs';

async function listen(server) {
  await new Promise(resolve => {
    server.listen(0, '127.0.0.1', resolve);
  });
  const { port } = server.address();
  return `http://127.0.0.1:${port}`;
}

async function close(server) {
  await new Promise((resolve, reject) => {
    server.close(error => (error ? reject(error) : resolve()));
  });
}

async function request(baseUrl, path, body, headers = {}) {
  return fetch(`${baseUrl}${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers:
      body === undefined
        ? headers
        : { 'Content-Type': 'application/json', ...headers },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

function createAutoMemStub() {
  const records = [];
  const recallQueries = [];
  let nextId = 1;
  const server = createServer(async (request, response) => {
    const chunks = [];
    for await (const chunk of request) {
      chunks.push(chunk);
    }
    const body = chunks.length
      ? JSON.parse(Buffer.concat(chunks).toString())
      : {};

    if (request.method === 'GET' && request.url === '/health') {
      response.writeHead(200, { 'Content-Type': 'application/json' });
      response.end(JSON.stringify({ status: 'healthy' }));
      return;
    }

    if (request.method === 'POST' && request.url === '/memory') {
      const record = {
        id: `memory-${nextId++}`,
        content: body.content,
        tags: body.tags,
        timestamp: body.timestamp,
        metadata: body.metadata,
        created_at: '2026-09-12T00:00:00.000Z',
      };
      records.push(record);
      response.writeHead(200, { 'Content-Type': 'application/json' });
      response.end(JSON.stringify({ status: 'success', memory_id: record.id }));
      return;
    }

    if (request.method === 'GET' && request.url.startsWith('/recall?')) {
      const url = new URL(request.url, 'http://localhost');
      recallQueries.push(url.searchParams);
      const tag = url.searchParams.get('tags');
      const query = url.searchParams.get('query').toLowerCase();
      const results = records
        .filter(record => record.tags.includes(tag))
        .filter(record => record.content.toLowerCase().includes(query))
        .map((record, index) => ({
          final_score: 1 - index / 10,
          memory: record,
        }));
      response.writeHead(200, { 'Content-Type': 'application/json' });
      response.end(JSON.stringify({ results }));
      return;
    }

    response.writeHead(404).end();
  });
  return { records, recallQueries, server };
}

const ADD_BODY = {
  request_id: 'eval:run-1:sample-1:chunk-0',
  user_id: 'eval:run-1:user-1',
  session_id: 'eval:run-1:session-1',
  messages: [
    {
      role: 'user',
      timestamp: 1704067200000,
      content: 'The launch codeword is juniper.',
    },
    {
      role: 'assistant',
      content: 'I will remember juniper for the launch.',
    },
  ],
};

async function withAdapter(options, run) {
  const automem = createAutoMemStub();
  const automemUrl = await listen(automem.server);
  const adapter = createAmlAdapterServer({ automemUrl, ...options });
  const adapterUrl = await listen(adapter);
  try {
    await run({ automem, adapterUrl });
  } finally {
    await close(adapter);
    await close(automem.server);
  }
}

test('AML Add persists messages synchronously and Search returns scoped evidence', async () => {
  await withAdapter(
    { automemApiKey: 'upstream', adapterApiKey: 'adapter-key' },
    async ({ automem, adapterUrl }) => {
      const health = await request(adapterUrl, '/health');
      assert.equal(health.status, 200);

      const add = await request(adapterUrl, '/add', ADD_BODY, {
        Authorization: 'Bearer adapter-key',
      });
      assert.equal(add.status, 200);
      assert.deepEqual(await add.json(), {
        success: true,
        request_id: ADD_BODY.request_id,
        user_id: ADD_BODY.user_id,
        session_id: ADD_BODY.session_id,
      });
      assert.equal(automem.records.length, 2);
      assert.equal(automem.records[0].timestamp, '2024-01-01T00:00:00.000Z');
      assert.deepEqual(automem.records[1].metadata, {
        aml_request_id: ADD_BODY.request_id,
        aml_session_id: ADD_BODY.session_id,
        aml_message_index: 1,
        aml_role: 'assistant',
      });

      const search = await request(
        adapterUrl,
        '/search',
        { query: 'juniper', user_id: ADD_BODY.user_id, top_k: 1 },
        { 'X-Api-Key': 'adapter-key' }
      );
      assert.equal(search.status, 200);
      const result = await search.json();
      assert.equal(result.data.length, 1);
      assert.equal(result.data[0].id, 'memory-1');
      assert.match(result.data[0].content, /juniper/);
      assert.equal(result.data[0].score, 1);

      const isolated = await request(
        adapterUrl,
        '/search',
        { query: 'juniper', user_id: 'eval:run-1:other-user', top_k: 100 },
        { Authorization: 'Token adapter-key' }
      );
      assert.deepEqual(await isolated.json(), { data: [] });
    }
  );
});

test('Search pins every isolation-relevant recall option', async () => {
  await withAdapter({}, async ({ automem, adapterUrl }) => {
    await request(adapterUrl, '/add', ADD_BODY);
    const search = await request(adapterUrl, '/search', {
      query: 'juniper',
      user_id: ADD_BODY.user_id,
      top_k: 500,
    });
    assert.equal(search.status, 200);
    const sent = automem.recallQueries.at(-1);
    assert.equal(sent.get('tag_match'), 'exact');
    assert.equal(sent.get('expand_relations'), 'false');
    assert.equal(sent.get('expand_entities'), 'false');
    assert.equal(sent.get('scope_fallback'), 'false');
    assert.equal(sent.get('limit'), '100');
  });
  assert.equal(
    recallParams({ query: 'q', userId: 'u', topK: 5 }).get('limit'),
    '5'
  );
});

test('Add is idempotent per request_id and rejects a conflicting replay', async () => {
  await withAdapter({}, async ({ automem, adapterUrl }) => {
    const first = await request(adapterUrl, '/add', ADD_BODY);
    assert.equal(first.status, 200);
    const replay = await request(adapterUrl, '/add', ADD_BODY);
    assert.equal(replay.status, 200);
    assert.equal(automem.records.length, 2);

    const conflict = await request(adapterUrl, '/add', {
      ...ADD_BODY,
      messages: [{ role: 'user', content: 'different content' }],
    });
    assert.equal(conflict.status, 409);
    assert.equal(automem.records.length, 2);
  });
});

test('Streaming Add persists incremental messages in source order', async () => {
  const firstContent = 'The first incremental fact arrives first.';
  const secondContent = 'The second incremental fact arrives second.';
  await withAdapter(
    {
      fetchImpl: async (url, options) => {
        if (url.endsWith('/memory')) {
          const { content } = JSON.parse(options.body);
          if (content.includes(firstContent)) {
            await new Promise(resolve => setTimeout(resolve, 20));
          }
        }
        return fetch(url, options);
      },
    },
    async ({ automem, adapterUrl }) => {
      const add = await request(adapterUrl, '/add', {
        ...ADD_BODY,
        request_id: 'eval:run-1:streaming:chunk-0',
        messages: [
          { role: 'user', content: firstContent },
          { role: 'assistant', content: secondContent },
        ],
      });
      assert.equal(add.status, 200);
      assert.deepEqual(
        automem.records.map(record => record.content),
        [`[user] ${firstContent}`, `[assistant] ${secondContent}`]
      );
    }
  );
});

test('Concurrent retries of one Add request write its messages once', async () => {
  await withAdapter(
    {
      fetchImpl: async (url, options) => {
        if (url.endsWith('/memory')) {
          await new Promise(resolve => setTimeout(resolve, 20));
        }
        return fetch(url, options);
      },
    },
    async ({ automem, adapterUrl }) => {
      const [first, retry] = await Promise.all([
        request(adapterUrl, '/add', ADD_BODY),
        request(adapterUrl, '/add', ADD_BODY),
      ]);
      assert.equal(first.status, 200);
      assert.equal(retry.status, 200);
      assert.equal(automem.records.length, ADD_BODY.messages.length);
    }
  );
});

test('AML adapter rejects missing required contract fields and invalid credentials', async () => {
  await withAdapter(
    { adapterApiKey: 'adapter-key' },
    async ({ adapterUrl }) => {
      const unauthorized = await request(adapterUrl, '/add', {
        request_id: 'request',
        user_id: 'user',
        session_id: 'session',
        messages: [{ role: 'user', content: 'memory' }],
      });
      assert.equal(unauthorized.status, 401);

      const invalid = await request(
        adapterUrl,
        '/search',
        { query: '', user_id: 'user', top_k: 100 },
        { Authorization: 'Bearer adapter-key' }
      );
      assert.equal(invalid.status, 422);
      assert.deepEqual(await invalid.json(), {
        detail: { reason: 'query must be a non-empty string' },
      });

      const oversized = await request(
        adapterUrl,
        '/add',
        { ...ADD_BODY, messages: [{ role: 'user', content: 'x'.repeat(1_100_000) }] },
        { Authorization: 'Bearer adapter-key' }
      );
      assert.equal(oversized.status, 413);
    }
  );
});

test('Health reports 503 when AutoMem is unreachable', async () => {
  const adapter = createAmlAdapterServer({
    automemUrl: 'http://127.0.0.1:9',
  });
  const adapterUrl = await listen(adapter);
  try {
    const health = await request(adapterUrl, '/health');
    assert.equal(health.status, 503);
  } finally {
    await close(adapter);
  }
});
