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
        aml_message_chunk_index: 0,
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

test('A retry after a partial Add failure resumes without duplicating its prefix', async () => {
  let failSecondWrite = true;
  await withAdapter(
    {
      fetchImpl: async (url, options) => {
        if (url.endsWith('/memory')) {
          const { content } = JSON.parse(options.body);
          if (failSecondWrite && content.includes('remember juniper')) {
            failSecondWrite = false;
            return new Response(null, { status: 503 });
          }
        }
        return fetch(url, options);
      },
    },
    async ({ automem, adapterUrl }) => {
      const failed = await request(adapterUrl, '/add', ADD_BODY);
      assert.equal(failed.status, 503);
      assert.equal(automem.records.length, 1);

      const retry = await request(adapterUrl, '/add', ADD_BODY);
      assert.equal(retry.status, 200);
      assert.equal(automem.records.length, ADD_BODY.messages.length);
      assert.deepEqual(
        automem.records.map(record => record.content),
        [
          '[user | 2024-01-01T00:00:00.000Z] The launch codeword is juniper.',
          '[assistant] I will remember juniper for the launch.',
        ]
      );
    }
  );
});

test('Add splits a valid long message to AutoMem-safe chunks', async () => {
  const content = 'x'.repeat(5_000);
  await withAdapter({}, async ({ automem, adapterUrl }) => {
    const add = await request(adapterUrl, '/add', {
      ...ADD_BODY,
      request_id: 'eval:run-1:long-message',
      messages: [{ role: 'user', content }],
    });
    assert.equal(add.status, 200);
    assert.ok(automem.records.length > 1);
    assert.ok(automem.records.every(record => record.content.length <= 2_000));
    assert.equal(
      automem.records.map(record => record.content.replace(/^\[user\] /, '')).join(''),
      content
    );
    assert.deepEqual(
      automem.records.map(record => record.metadata.aml_message_chunk_index),
      [0, 1, 2]
    );
  });
});

test('Add preserves non-BMP characters at chunk boundaries', async () => {
  const content = `${'😀'.repeat(1_992)}abcdef`;
  await withAdapter({}, async ({ automem, adapterUrl }) => {
    const add = await request(adapterUrl, '/add', {
      ...ADD_BODY,
      request_id: 'eval:run-1:unicode-message',
      messages: [{ role: 'user', content }],
    });
    assert.equal(add.status, 200);
    assert.equal(
      automem.records.map(record => record.content.replace(/^\[user\] /, '')).join(''),
      content
    );
  });
});

test('incremental Adds in one session are immediately searchable and retry safely', async () => {
  await withAdapter({}, async ({ automem, adapterUrl }) => {
    const firstChunk = {
      request_id: 'eval:run-1:sample-1:chunk-0',
      user_id: 'eval:run-1:user-streaming',
      session_id: 'eval:run-1:session-streaming',
      messages: [
        { role: 'user', content: 'The first streaming detail is tangerine.' },
      ],
    };
    const secondChunk = {
      ...firstChunk,
      request_id: 'eval:run-1:sample-1:chunk-1',
      messages: [
        { role: 'assistant', content: 'The next streaming detail is violet.' },
      ],
    };

    assert.equal((await request(adapterUrl, '/add', firstChunk)).status, 200);
    const afterFirstChunk = await request(adapterUrl, '/search', {
      query: 'tangerine',
      user_id: firstChunk.user_id,
      top_k: 10,
    });
    assert.equal(afterFirstChunk.status, 200);
    assert.match((await afterFirstChunk.json()).data[0].content, /tangerine/);

    assert.equal((await request(adapterUrl, '/add', secondChunk)).status, 200);
    const afterSecondChunk = await request(adapterUrl, '/search', {
      query: 'violet',
      user_id: secondChunk.user_id,
      top_k: 10,
    });
    assert.equal(afterSecondChunk.status, 200);
    assert.match((await afterSecondChunk.json()).data[0].content, /violet/);

    assert.equal((await request(adapterUrl, '/add', secondChunk)).status, 200);
    assert.equal(automem.records.length, 2);
  });
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

test('Health applies the configured upstream timeout', async () => {
  const adapter = createAmlAdapterServer({
    automemUrl: 'http://automem.test',
    upstreamTimeoutMs: 10,
    fetchImpl: async (_url, { signal }) =>
      new Promise((resolve, reject) => {
        signal.addEventListener('abort', () => reject(signal.reason));
      }),
  });
  const adapterUrl = await listen(adapter);
  try {
    const health = await request(adapterUrl, '/health');
    assert.equal(health.status, 503);
  } finally {
    await close(adapter);
  }
});
