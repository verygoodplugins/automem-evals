#!/usr/bin/env node
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';

import { createAmlAdapterServer } from './adapter.mjs';

const automemUrl = process.env.AUTOMEM_API_URL;
const automemApiKey = process.env.AUTOMEM_API_KEY;

if (!automemUrl || !automemApiKey) {
  throw new Error('AUTOMEM_API_URL and AUTOMEM_API_KEY are required');
}

function upstreamHeaders() {
  return {
    Authorization: `Bearer ${automemApiKey}`,
    'Content-Type': 'application/json',
  };
}

async function listen(server) {
  await new Promise(resolve => {
    server.listen(0, '127.0.0.1', resolve);
  });
  return `http://127.0.0.1:${server.address().port}`;
}

async function close(server) {
  await new Promise((resolve, reject) => {
    server.close(error => (error ? reject(error) : resolve()));
  });
}

const token = randomUUID();
const adapterKey = randomUUID();
const userId = `aml-smoke-${token}`;
const content = `AML adapter smoke sentinel ${token}`;
const server = createAmlAdapterServer({
  automemUrl,
  automemApiKey,
  adapterApiKey: adapterKey,
});
const createdIds = [];

try {
  const baseUrl = await listen(server);
  const add = await fetch(`${baseUrl}/add`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${adapterKey}`,
    },
    body: JSON.stringify({
      request_id: `aml-smoke:${token}`,
      user_id: userId,
      session_id: `aml-smoke-session:${token}`,
      messages: [{ role: 'user', timestamp: Date.now(), content }],
    }),
  });
  assert.equal(add.status, 200);

  const search = await fetch(`${baseUrl}/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Api-Key': adapterKey },
    body: JSON.stringify({ query: token, user_id: userId, top_k: 1 }),
  });
  assert.equal(search.status, 200);
  const { data } = await search.json();
  assert.equal(data.length, 1);
  assert.match(data[0].content, new RegExp(token));
  createdIds.push(data[0].id);

  const isolated = await fetch(`${baseUrl}/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Api-Key': adapterKey },
    body: JSON.stringify({
      query: token,
      user_id: `${userId}-other`,
      top_k: 1,
    }),
  });
  assert.deepEqual(await isolated.json(), { data: [] });

  process.stdout.write('AML adapter real-AutoMem Add/Search smoke: PASS\n');
} finally {
  await Promise.all(
    createdIds.map(async memoryId => {
      await fetch(`${automemUrl.replace(/\/+$/, '')}/memory/${memoryId}`, {
        method: 'DELETE',
        headers: upstreamHeaders(),
      });
    })
  );
  await close(server);
}
