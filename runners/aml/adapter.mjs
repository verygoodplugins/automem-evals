import { createHash, timingSafeEqual } from 'node:crypto';
import { createServer } from 'node:http';

const JSON_HEADERS = { 'Content-Type': 'application/json; charset=utf-8' };
const DEFAULT_RETENTION_DAYS = 30;
const MAX_BODY_BYTES = 1_000_000;
// AutoMem caps recall limits server-side; clamp rather than reject so an AML
// top_k above the cap still gets the best evidence AutoMem can return.
const MAX_RECALL_LIMIT = 100;

function json(response, status, body) {
  response.writeHead(status, JSON_HEADERS);
  response.end(JSON.stringify(body));
}

function detail(response, status, reason) {
  json(response, status, { detail: { reason } });
}

class BodyTooLargeError extends Error {}

function userTag(userId) {
  const hash = createHash('sha256').update(userId).digest('base64url');
  return `aml-user-${hash}`;
}

function formatMessage(message) {
  const timestamp = Number.isFinite(message.timestamp)
    ? ` | ${new Date(message.timestamp).toISOString()}`
    : '';
  return `[${message.role}${timestamp}] ${message.content}`;
}

function getApiKey(request) {
  const xApiKey = request.headers['x-api-key'];
  if (typeof xApiKey === 'string' && xApiKey) {
    return xApiKey;
  }
  const authorization = request.headers.authorization;
  if (typeof authorization !== 'string') {
    return '';
  }
  const match = authorization.match(/^(?:Bearer|Token)\s+(.+)$/i);
  return match?.[1]?.trim() || '';
}

function keysMatch(received, expected) {
  if (!expected) {
    return true;
  }
  const receivedBuffer = Buffer.from(received);
  const expectedBuffer = Buffer.from(expected);
  return (
    receivedBuffer.length === expectedBuffer.length &&
    timingSafeEqual(receivedBuffer, expectedBuffer)
  );
}

async function readJson(request) {
  const chunks = [];
  let size = 0;
  for await (const chunk of request) {
    size += chunk.length;
    if (size > MAX_BODY_BYTES) {
      throw new BodyTooLargeError();
    }
    chunks.push(chunk);
  }
  try {
    return JSON.parse(Buffer.concat(chunks).toString('utf8'));
  } catch {
    return null;
  }
}

function invalidString(value, name) {
  return typeof value !== 'string' || !value.trim()
    ? `${name} must be a non-empty string`
    : null;
}

function validateAdd(body) {
  for (const name of ['request_id', 'user_id', 'session_id']) {
    const error = invalidString(body?.[name], name);
    if (error) {
      return error;
    }
  }
  if (!Array.isArray(body.messages) || body.messages.length === 0) {
    return 'messages must be a non-empty array';
  }
  for (const message of body.messages) {
    const roleError = invalidString(message?.role, 'messages[].role');
    const contentError = invalidString(message?.content, 'messages[].content');
    if (roleError || contentError) {
      return roleError || contentError;
    }
    if (
      message.timestamp !== undefined &&
      (!Number.isInteger(message.timestamp) || message.timestamp < 0)
    ) {
      return 'messages[].timestamp must be a Unix-millisecond integer';
    }
  }
  return null;
}

function validateSearch(body) {
  for (const name of ['query', 'user_id']) {
    const error = invalidString(body?.[name], name);
    if (error) {
      return error;
    }
  }
  if (!Number.isInteger(body.top_k) || body.top_k < 1) {
    return 'top_k must be a positive integer';
  }
  if (body.options !== undefined && !Array.isArray(body.options)) {
    return 'options must be an array when provided';
  }
  return null;
}

function requestFingerprint(body) {
  return createHash('sha256').update(JSON.stringify(body)).digest('hex');
}

function normalizeResults(payload, topK) {
  const results = Array.isArray(payload?.results) ? payload.results : [];
  return results
    .map(result => {
      const memory = result.memory || result;
      const id = String(
        memory?.id || memory?.memory_id || result?.id || ''
      ).trim();
      const content = String(memory?.content || memory?.summary || '').trim();
      if (!id || !content) {
        return null;
      }
      const item = { id, content };
      const score = Number(result?.final_score ?? result?.score ?? memory?.score);
      if (Number.isFinite(score)) {
        item.score = score;
      }
      const createdAt =
        memory?.created_at || memory?.createdAt || memory?.timestamp;
      if (typeof createdAt === 'string' && createdAt) {
        item.created_at = createdAt;
      }
      return item;
    })
    .filter(Boolean)
    .slice(0, topK);
}

function upstreamHeaders(automemApiKey) {
  return {
    'Content-Type': 'application/json',
    ...(automemApiKey ? { Authorization: `Bearer ${automemApiKey}` } : {}),
  };
}

/**
 * Query for one user's evidence. Every isolation-relevant recall option is
 * pinned explicitly rather than trusting server defaults: exact tag match (the
 * server default is prefix), and no relation expansion, entity expansion, or
 * unscoped scope fallback — each of which can return another user's records.
 */
export function recallParams({ query, userId, topK }) {
  return new URLSearchParams({
    query,
    tags: userTag(userId),
    tag_match: 'exact',
    expand_relations: 'false',
    expand_entities: 'false',
    scope_fallback: 'false',
    limit: String(Math.min(topK, MAX_RECALL_LIMIT)),
  });
}

/**
 * Creates the AML-compatible HTTP wrapper around AutoMem's REST API.
 * This service intentionally provides only AML's /health, /add, and /search
 * endpoints; it neither answers questions nor exposes AutoMem administration.
 */
export function createAmlAdapterServer({
  automemUrl,
  automemApiKey = '',
  adapterApiKey = '',
  fetchImpl = fetch,
  retentionDays = DEFAULT_RETENTION_DAYS,
} = {}) {
  if (!automemUrl) {
    throw new Error('AUTOMEM_API_URL is required');
  }

  const baseUrl = automemUrl.replace(/\/+$/, '');
  const completedAdds = new Map();

  return createServer(async (request, response) => {
    const { pathname } = new URL(request.url || '/', 'http://localhost');

    if (request.method === 'GET' && pathname === '/health') {
      try {
        const upstream = await fetchImpl(`${baseUrl}/health`, {
          headers: upstreamHeaders(automemApiKey),
        });
        if (upstream.ok) {
          json(response, 200, { status: 'ok' });
          return;
        }
      } catch {
        // fall through to the unavailable response
      }
      detail(response, 503, 'AutoMem is unavailable');
      return;
    }

    if (request.method !== 'POST' || !['/add', '/search'].includes(pathname)) {
      detail(response, 404, 'not found');
      return;
    }

    if (!keysMatch(getApiKey(request), adapterApiKey)) {
      detail(response, 401, 'invalid API key');
      return;
    }

    let body;
    try {
      body = await readJson(request);
    } catch (error) {
      if (error instanceof BodyTooLargeError) {
        detail(response, 413, `request body exceeds ${MAX_BODY_BYTES} bytes`);
        return;
      }
      detail(response, 400, 'request body could not be read');
      return;
    }
    if (!body || Array.isArray(body)) {
      detail(response, 400, 'request body must be a JSON object');
      return;
    }

    const validationError =
      pathname === '/add' ? validateAdd(body) : validateSearch(body);
    if (validationError) {
      detail(response, 422, validationError);
      return;
    }

    try {
      if (pathname === '/add') {
        const fingerprint = requestFingerprint(body);
        const existing = completedAdds.get(body.request_id);
        if (existing) {
          if (existing.fingerprint !== fingerprint) {
            detail(
              response,
              409,
              'request_id was already used with different content'
            );
            return;
          }
          json(response, 200, existing.response);
          return;
        }

        const expiresAt = new Date(
          Date.now() + retentionDays * 24 * 60 * 60 * 1000
        ).toISOString();
        const tags = ['aml-evaluation', userTag(body.user_id)];
        const writes = await Promise.all(
          body.messages.map((message, index) =>
            fetchImpl(`${baseUrl}/memory`, {
              method: 'POST',
              headers: upstreamHeaders(automemApiKey),
              body: JSON.stringify({
                content: formatMessage(message),
                type: 'Context',
                tags,
                importance: 0.5,
                confidence: 0.8,
                t_invalid: expiresAt,
                ...(Number.isFinite(message.timestamp)
                  ? { timestamp: new Date(message.timestamp).toISOString() }
                  : {}),
                metadata: {
                  aml_request_id: body.request_id,
                  aml_session_id: body.session_id,
                  aml_message_index: index,
                  aml_role: message.role,
                },
              }),
            })
          )
        );
        if (writes.some(upstream => !upstream.ok)) {
          detail(response, 503, 'AutoMem could not persist the memory');
          return;
        }

        const success = {
          success: true,
          request_id: body.request_id,
          user_id: body.user_id,
          session_id: body.session_id,
        };
        completedAdds.set(body.request_id, { fingerprint, response: success });
        json(response, 200, success);
        return;
      }

      const params = recallParams({
        query: body.query,
        userId: body.user_id,
        topK: body.top_k,
      });
      const upstream = await fetchImpl(`${baseUrl}/recall?${params}`, {
        headers: automemApiKey
          ? { Authorization: `Bearer ${automemApiKey}` }
          : {},
      });
      if (!upstream.ok) {
        detail(response, 503, 'AutoMem could not retrieve memories');
        return;
      }
      json(response, 200, {
        data: normalizeResults(await upstream.json(), body.top_k),
      });
    } catch {
      detail(response, 503, 'AutoMem is unavailable');
    }
  });
}
