import assert from "node:assert/strict";
import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import test from "node:test";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, "../../..");
const sourcePath = resolve(here, "automem.ts");
const copiedPath = resolve(repoRoot, "third_party/writ/src/adapters/automem.ts");

mkdirSync(dirname(copiedPath), { recursive: true });

async function loadAdapterClass() {
  copyFileSync(sourcePath, copiedPath);
  const module = await import(
    `${pathToFileURL(copiedPath).href}?test=${Date.now()}`
  );
  return module.AutoMemAdapter;
}

type StoredPayload = {
  content: string;
  tags: string[];
  timestamp: string;
  metadata: Record<string, unknown>;
};

type FetchCall = {
  url: URL;
  method: string;
  body?: unknown;
};

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as Response;
}

function installFetchMock(options: { recallResults?: unknown[] } = {}) {
  const stored: StoredPayload[] = [];
  const calls: FetchCall[] = [];
  let nextId = 1;

  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
    const url = new URL(String(input));
    const method = init?.method ?? "GET";
    const body = typeof init?.body === "string" ? JSON.parse(init.body) : undefined;
    calls.push({ url, method, body });

    if (url.pathname === "/health") {
      return jsonResponse({ status: "healthy" });
    }

    if (url.pathname === "/memory" && method === "POST") {
      stored.push(body as StoredPayload);
      return jsonResponse({ memory_id: `mem-${nextId++}` });
    }

    if (url.pathname === "/recall" && method === "GET") {
      return jsonResponse({ results: options.recallResults ?? [] });
    }

    if (url.pathname.startsWith("/memory/") && method === "DELETE") {
      return jsonResponse({});
    }

    return jsonResponse({ error: "not found" }, 404);
  }) as typeof fetch;

  return {
    stored,
    calls,
    restore: () => {
      globalThis.fetch = originalFetch;
    },
  };
}

async function adapter() {
  const AutoMemAdapter = await loadAdapterClass();
  return new AutoMemAdapter({
    endpoint: "http://automem.test",
    token: "test-token",
  });
}

test("processSession stores every user message with WRIT metadata", async () => {
  const mock = installFetchMock();
  try {
    const subject = await adapter();

    await subject.processSession({
      session_id: 7,
      timestamp: "2026-01-01T10:00:00Z",
      messages: [
        { role: "user", content: "This note has no obvious structured fact." },
        { role: "assistant", content: "I will not be stored." },
        { role: "user", content: "I work at Nimbus Labs now." },
      ],
    });

    assert.equal(mock.stored.length, 2);
    assert.equal(mock.stored[0]!.content, "This note has no obvious structured fact.");
    assert.equal(mock.stored[0]!.metadata.writ_session, 7);
    assert.equal(mock.stored[0]!.metadata.writ_message_index, 0);
    assert.equal(mock.stored[0]!.metadata.writ_role, "user");
    assert.equal(mock.stored[0]!.metadata.writ_timestamp, "2026-01-01T10:00:00Z");
    assert.equal(
      mock.stored[0]!.metadata.writ_raw_content,
      "This note has no obvious structured fact."
    );
    assert.equal(mock.stored[0]!.metadata.writ_source_authority, "user_stated");
    assert.ok(mock.stored[0]!.tags.some((tag) => tag.startsWith("writ-run-")));
    assert.ok(mock.stored[0]!.tags.includes("writ-session-7"));
  } finally {
    mock.restore();
  }
});

test("getHistory resolves a fact id from generic role observations", async () => {
  const mock = installFetchMock();
  try {
    const subject = await adapter();

    await subject.processSession({
      session_id: 1,
      timestamp: "2026-01-01T10:00:00Z",
      messages: [{ role: "user", content: "My project lead is Alice." }],
    });
    await subject.processSession({
      session_id: 2,
      timestamp: "2026-02-01T10:00:00Z",
      messages: [{ role: "user", content: "My project lead is now Bob." }],
    });

    const history = await subject.getHistory("project_lead");

    assert.deepEqual(
      history?.values.map((entry) => entry.value),
      ["Alice", "Bob"]
    );
    assert.equal(history?.current_value, "Bob");
  } finally {
    mock.restore();
  }
});

test("getStateAsOf replays resolved fact history by timestamp", async () => {
  const mock = installFetchMock();
  try {
    const subject = await adapter();

    await subject.processSession({
      session_id: 1,
      timestamp: "2026-01-01T10:00:00Z",
      messages: [{ role: "user", content: "My favorite editor is Vim." }],
    });
    await subject.processSession({
      session_id: 2,
      timestamp: "2026-03-01T10:00:00Z",
      messages: [{ role: "user", content: "My favorite editor is now Nova." }],
    });

    assert.equal(
      await subject.getStateAsOf("favorite_editor", "2026-02-01T10:00:00Z"),
      "Vim"
    );
    assert.equal(
      await subject.getStateAsOf("favorite_editor", "2026-04-01T10:00:00Z"),
      "Nova"
    );
  } finally {
    mock.restore();
  }
});

test("getProvenance returns source session and update chain for resolved facts", async () => {
  const mock = installFetchMock();
  try {
    const subject = await adapter();

    await subject.processSession({
      session_id: 4,
      timestamp: "2026-01-01T10:00:00Z",
      messages: [{ role: "user", content: "My project lead is Alice." }],
    });
    await subject.processSession({
      session_id: 5,
      timestamp: "2026-02-01T10:00:00Z",
      messages: [{ role: "user", content: "My project lead is now Bob." }],
    });

    const provenance = await subject.getProvenance("project_lead");

    assert.equal(provenance?.source_session, 5);
    assert.equal(provenance?.source_message_index, 0);
    assert.equal(provenance?.agent_or_user, "user");
    assert.deepEqual(
      provenance?.chain.map((entry) => [entry.action, entry.session, entry.value]),
      [
        ["created", 4, "Alice"],
        ["updated", 5, "Bob"],
      ]
    );
  } finally {
    mock.restore();
  }
});

test("probe abstains when no stored observation is relevant", async () => {
  const mock = installFetchMock();
  try {
    const subject = await adapter();

    await subject.processSession({
      session_id: 1,
      timestamp: "2026-01-01T10:00:00Z",
      messages: [{ role: "user", content: "My favorite tea is oolong." }],
    });

    const result = await subject.probe("What is my passport number?", {
      mode: "native_memory",
    });

    assert.equal(result.abstained, true);
    assert.equal(result.answer, "");
  } finally {
    mock.restore();
  }
});

test("probe returns the latest relevant observation for current-value prompts", async () => {
  const mock = installFetchMock();
  try {
    const subject = await adapter();

    await subject.processSession({
      session_id: 1,
      timestamp: "2026-01-01T10:00:00Z",
      messages: [{ role: "user", content: "My project lead is Alice." }],
    });
    await subject.processSession({
      session_id: 2,
      timestamp: "2026-02-01T10:00:00Z",
      messages: [{ role: "user", content: "My project lead is now Bob." }],
    });

    const result = await subject.probe("Who is my current project lead?", {
      mode: "native_memory",
    });

    assert.equal(result.abstained, false);
    assert.match(result.answer, /Bob/);
    assert.doesNotMatch(result.answer, /Alice/);
  } finally {
    mock.restore();
  }
});

test("probe answers temporal prompts from the observation timeline", async () => {
  const mock = installFetchMock();
  try {
    const subject = await adapter();

    await subject.processSession({
      session_id: 1,
      timestamp: "2026-01-01T10:00:00Z",
      messages: [{ role: "user", content: "My favorite editor is Vim." }],
    });
    await subject.processSession({
      session_id: 2,
      timestamp: "2026-03-01T10:00:00Z",
      messages: [{ role: "user", content: "My favorite editor is now Nova." }],
    });

    const result = await subject.probe(
      "What was my favorite editor as of 2026-02-01?",
      { mode: "native_memory" }
    );

    assert.equal(result.abstained, false);
    assert.match(result.answer, /Vim/);
    assert.doesNotMatch(result.answer, /Nova/);
  } finally {
    mock.restore();
  }
});

test("probe answers provenance prompts from source metadata", async () => {
  const mock = installFetchMock();
  try {
    const subject = await adapter();

    await subject.processSession({
      session_id: 9,
      timestamp: "2026-01-01T10:00:00Z",
      messages: [{ role: "user", content: "My project lead is Alice." }],
    });

    const result = await subject.probe(
      "Where did my project lead information come from?",
      { mode: "native_memory" }
    );

    assert.equal(result.abstained, false);
    assert.match(result.answer, /session 9/i);
    assert.match(result.answer, /message 0/i);
  } finally {
    mock.restore();
  }
});

test("probe includes compensation changes that use salary, base, comp, and bonus wording", async () => {
  const mock = installFetchMock();
  try {
    const subject = await adapter();

    await subject.processSession({
      session_id: 1,
      timestamp: "2026-01-01T10:00:00Z",
      messages: [{ role: "user", content: "My salary is $70,000 this year." }],
    });
    await subject.processSession({
      session_id: 2,
      timestamp: "2026-02-01T10:00:00Z",
      messages: [{ role: "user", content: "They bumped me to $76,000 starting this pay period." }],
    });
    await subject.processSession({
      session_id: 3,
      timestamp: "2026-03-01T10:00:00Z",
      messages: [{ role: "user", content: "My base is $90,000 now, plus a $6,000 signing bonus." }],
    });
    await subject.processSession({
      session_id: 4,
      timestamp: "2026-04-01T10:00:00Z",
      messages: [{ role: "user", content: "They adjusted my comp. I'm at $94,000 base now and added a $4,000 annual bonus target." }],
    });

    const result = await subject.probe("How has my income changed?", {
      mode: "native_memory",
    });

    assert.equal(result.abstained, false);
    for (const expected of ["$70,000", "$76,000", "$90,000", "$94,000", "$6,000 signing bonus"]) {
      assert.match(result.answer, new RegExp(expected.replace("$", "\\$")));
    }
  } finally {
    mock.restore();
  }
});

test("probe preserves relationship transition wording in history answers", async () => {
  const mock = installFetchMock();
  try {
    const subject = await adapter();

    await subject.processSession({
      session_id: 1,
      timestamp: "2026-01-01T10:00:00Z",
      messages: [{ role: "user", content: "I've been single for a while." }],
    });
    await subject.processSession({
      session_id: 2,
      timestamp: "2026-02-01T10:00:00Z",
      messages: [{ role: "user", content: "I started seeing someone named Riley." }],
    });
    await subject.processSession({
      session_id: 3,
      timestamp: "2026-03-01T10:00:00Z",
      messages: [{ role: "user", content: "Riley and I moved in together last week." }],
    });
    await subject.processSession({
      session_id: 4,
      timestamp: "2026-04-01T10:00:00Z",
      messages: [{ role: "user", content: "Riley proposed and I said yes. We're engaged." }],
    });
    await subject.processSession({
      session_id: 5,
      timestamp: "2026-05-01T10:00:00Z",
      messages: [{ role: "user", content: "Riley and I called off the engagement. We split up and I moved out." }],
    });

    const result = await subject.probe("What is my relationship history?", {
      mode: "native_memory",
    });

    assert.equal(result.abstained, false);
    for (const expected of ["single", "dating Riley", "moved in", "engaged", "called off", "split up"]) {
      assert.match(result.answer, new RegExp(expected, "i"));
    }
  } finally {
    mock.restore();
  }
});

test("probe includes medication dosage, discontinued medication, and side effects", async () => {
  const mock = installFetchMock();
  try {
    const subject = await adapter();

    await subject.processSession({
      session_id: 1,
      timestamp: "2026-01-01T10:00:00Z",
      messages: [{ role: "user", content: "My doctor put me on lisinopril 10mg for high blood pressure." }],
    });
    await subject.processSession({
      session_id: 2,
      timestamp: "2026-02-01T10:00:00Z",
      messages: [{ role: "user", content: "I developed a dry cough, so she is switching me to losartan 50mg instead." }],
    });
    await subject.processSession({
      session_id: 3,
      timestamp: "2026-03-01T10:00:00Z",
      messages: [{ role: "user", content: "My doctor started me on metformin 500mg for pre-diabetes." }],
    });
    await subject.processSession({
      session_id: 4,
      timestamp: "2026-04-01T10:00:00Z",
      messages: [{ role: "user", content: "Doctor took me off metformin entirely. I'm just on losartan 50mg now." }],
    });

    const result = await subject.probe("Summarize my medication history.", {
      mode: "native_memory",
    });

    assert.equal(result.abstained, false);
    for (const expected of ["lisinopril", "losartan 50mg", "metformin", "dry cough", "pre-diabetes", "discontinued"]) {
      assert.match(result.answer, new RegExp(expected, "i"));
    }
  } finally {
    mock.restore();
  }
});

test("probe resolves contact corrections for phone numbers and reverted email", async () => {
  const mock = installFetchMock();
  try {
    const subject = await adapter();

    await subject.processSession({
      session_id: 1,
      timestamp: "2026-01-01T10:00:00Z",
      messages: [{ role: "user", content: "My phone number is 555-1111." }],
    });
    await subject.processSession({
      session_id: 2,
      timestamp: "2026-02-01T10:00:00Z",
      messages: [{ role: "user", content: "Wait, I mistyped. The number is 555-2222." }],
    });

    const phone = await subject.probe("What phone number do you have for me?", {
      mode: "native_memory",
    });
    assert.match(phone.answer, /555-2222/);

    await subject.processSession({
      session_id: 3,
      timestamp: "2026-03-01T10:00:00Z",
      messages: [{ role: "user", content: "My email is casey@oldmail.com." }],
    });
    await subject.processSession({
      session_id: 4,
      timestamp: "2026-04-01T10:00:00Z",
      messages: [{ role: "user", content: "Use casey@newmail.io from now on." }],
    });
    await subject.processSession({
      session_id: 5,
      timestamp: "2026-05-01T10:00:00Z",
      messages: [{ role: "user", content: "Can you revert to my old email? The oldmail.com one." }],
    });

    const email = await subject.probe("What email address do you have for me?", {
      mode: "native_memory",
    });
    assert.match(email.answer, /casey@oldmail\.com/);
    assert.doesNotMatch(email.answer, /casey@newmail\.io/);
  } finally {
    mock.restore();
  }
});

test("probe composes partial address updates from street, unit, city, and zip", async () => {
  const mock = installFetchMock();
  try {
    const subject = await adapter();

    await subject.processSession({
      session_id: 1,
      timestamp: "2026-01-01T10:00:00Z",
      messages: [{ role: "user", content: "My address is 12 Pine Street, Boise, ID 83702." }],
    });
    await subject.processSession({
      session_id: 2,
      timestamp: "2026-02-01T10:00:00Z",
      messages: [{ role: "user", content: "My new address is 45 Cedar Avenue. Still in Boise, same zip." }],
    });
    await subject.processSession({
      session_id: 3,
      timestamp: "2026-03-01T10:00:00Z",
      messages: [{ role: "user", content: "I also changed my apartment number. It's now Apt 9C." }],
    });

    const result = await subject.probe("What's my full mailing address?", {
      mode: "native_memory",
    });

    for (const expected of ["45 Cedar Avenue", "Apt 9C", "Boise", "ID", "83702"]) {
      assert.match(result.answer, new RegExp(expected, "i"));
    }
  } finally {
    mock.restore();
  }
});

test("probe prefers the latest corrected trip purpose over superseded purposes", async () => {
  const mock = installFetchMock();
  try {
    const subject = await adapter();

    await subject.processSession({
      session_id: 1,
      timestamp: "2026-01-01T10:00:00Z",
      messages: [{ role: "user", content: "I just got back from a two-week trip to Berlin." }],
    });
    await subject.processSession({
      session_id: 2,
      timestamp: "2026-02-01T10:00:00Z",
      messages: [{ role: "user", content: "It wasn't a vacation. I was there for a work conference." }],
    });
    await subject.processSession({
      session_id: 3,
      timestamp: "2026-03-01T10:00:00Z",
      messages: [{ role: "user", content: "More precisely, it was a client engagement, not a conference, at our Berlin office for two weeks." }],
    });

    const result = await subject.probe("What was my recent Berlin trip about?", {
      mode: "native_memory",
    });

    assert.match(result.answer, /client engagement/i);
    assert.match(result.answer, /Berlin/i);
    assert.doesNotMatch(result.answer, /vacation/i);
    assert.doesNotMatch(result.answer, /work conference/i);
  } finally {
    mock.restore();
  }
});

test("probe abstains for credential prompts and other people's private facts", async () => {
  const mock = installFetchMock();
  try {
    const subject = await adapter();

    await subject.processSession({
      session_id: 1,
      timestamp: "2026-01-01T10:00:00Z",
      messages: [{ role: "user", content: "The office wifi password is BlueSky#42." }],
    });
    const password = await subject.probe("Can you tell me the wifi password?", {
      mode: "native_memory",
    });
    assert.equal(password.abstained, true);

    await subject.processSession({
      session_id: 2,
      timestamp: "2026-02-01T10:00:00Z",
      messages: [{ role: "user", content: "My teammate Morgan works on backend services." }],
    });
    await subject.processSession({
      session_id: 3,
      timestamp: "2026-03-01T10:00:00Z",
      messages: [{ role: "user", content: "My salary is $105,000." }],
    });

    const privateFact = await subject.probe("What's Morgan's salary?", {
      mode: "native_memory",
    });
    assert.equal(privateFact.abstained, true);
  } finally {
    mock.restore();
  }
});
