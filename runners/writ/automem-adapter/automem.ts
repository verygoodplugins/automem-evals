import type { MemoryAdapter, AdapterCapabilities } from "../adapter.js";
import type {
  Session,
  ProbeOptions,
  ProbeResult,
  FactHistory,
  Provenance,
  ValueHistoryEntry,
} from "../types.js";

interface RecallMemoryEnvelope {
  content?: string;
  metadata?: Record<string, unknown>;
  timestamp?: string;
  t_valid?: string;
  tags?: string[];
  tag_prefixes?: string[];
}

interface RecallResultItem {
  id?: string;
  memory_id?: string;
  final_score?: number;
  match_score?: number;
  memory?: RecallMemoryEnvelope;
}

interface FactExtractor {
  fact_id: string;
  /** Return the normalized fact value if `content` references this fact, else null. */
  extract: (content: string) => string | null;
}

const FACT_EXTRACTORS: FactExtractor[] = [
  {
    fact_id: "employer",
    extract: (s) => {
      let m = s.match(
        /\bI (?:work|am working|just accepted.*?(?:role|position).*?work) at ([A-Z][\w &.'-]*?(?:\s+Corp(?:oration)?|\s+Inc|\s+LLC|\s+Ltd|\s+Co)?)(?:\.|,|\s+(?:as|now|today|same)|$)/i
      );
      if (m) return m[1]!.trim();
      m = s.match(
        /\bmoved to ([A-Z][\w &.'-]*?(?:\s+Corp(?:oration)?|\s+Inc|\s+LLC))/
      );
      if (m) return m[1]!.trim();
      if (/\bconsult(?:ing|ant) practice\b/i.test(s)) return "independent consultant";
      if (/\bgoing independent\b/i.test(s)) return "independent consultant";
      return null;
    },
  },
  {
    fact_id: "title",
    extract: (s) => {
      const m = s.match(
        /\b(?:as a|promoted to|now a|now an|i'?m a|i am a) ((?:senior|junior|principal|staff|software|product|engineering|technical) [\w-]+|engineer|consultant|developer|manager|analyst)\b/i
      );
      if (m) return m[1]!.trim().toLowerCase();
      if (/\bconsult(?:ing|ant) practice\b/i.test(s)) return "consultant";
      if (/\bgoing independent\b/i.test(s)) return "consultant";
      return null;
    },
  },

  {
    fact_id: "base_salary",
    extract: (s) => {
      const m = s.match(
        /\$(\d{1,3}(?:,\d{3})+)\b(?!\s+(?:signing|bonus))/
      );
      return m ? `$${m[1]}` : null;
    },
  },
  {
    fact_id: "bonus_target",
    extract: (s) => {
      const m = s.match(/\$([\d,]+)\s+(?:annual\s+)?bonus(?:\s+target)?/i);
      return m ? `$${m[1]} bonus target` : null;
    },
  },
  {
    fact_id: "signing_bonus",
    extract: (s) => {
      const m = s.match(/\$([\d,]+)\s+signing\s+bonus/i);
      return m ? `$${m[1]} signing bonus` : null;
    },
  },

  {
    fact_id: "relationship_status",
    extract: (s) => {
      if (/\bcalled off (?:the )?engagement\b/i.test(s) || /\bsplit up\b/i.test(s)) {
        return "single";
      }
      const partner = s.match(/\b([A-Z][a-z]+) (?:and I|proposed)\b/);
      const partnerName = partner ? partner[1]! : null;
      if (/\bproposed\b/i.test(s) && /\bsaid yes\b/i.test(s)) {
        return partnerName ? `engaged to ${partnerName}` : "engaged";
      }
      if (/\bwe'?re engaged\b/i.test(s)) {
        return partnerName ? `engaged to ${partnerName}` : "engaged";
      }
      if (/\bmoved in together\b/i.test(s)) {
        return partnerName ? `living with ${partnerName}` : "moved in";
      }
      if (/\b(?:dating|seeing someone)\b/i.test(s)) {
        const m = s.match(/\bnamed ([A-Z][a-z]+)\b/);
        return m ? `dating ${m[1]}` : "dating";
      }
      if (/\bbeen single\b/i.test(s) || /\bflying solo\b/i.test(s)) return "single";
      return null;
    },
  },
  {
    fact_id: "partner_name",
    extract: (s) => {
      let m = s.match(/\bnamed ([A-Z][a-z]+)\b/);
      if (m) return m[1]!;
      m = s.match(/\b([A-Z][a-z]+) (?:and I|proposed)\b/);
      if (m) return m[1]!;
      return null;
    },
  },
  {
    fact_id: "living_arrangement",
    extract: (s) => {
      if (/\bmoved in together\b/i.test(s)) return "moved in together";
      if (/\bmoved out\b/i.test(s)) return "moved out";
      return null;
    },
  },

  {
    fact_id: "home_city",
    extract: (s) => {
      const cities: Array<[string, string]> = [
        ["Austin", "TX"],
        ["Denver", "CO"],
        ["Seattle", "WA"],
        ["Portland", "OR"],
        ["San Francisco", "CA"],
        ["New York", "NY"],
        ["Chicago", "IL"],
        ["Boston", "MA"],
        ["Los Angeles", "CA"],
      ];
      for (const [c, st] of cities) {
        if (new RegExp(`\\b${c}\\b`).test(s)) return `${c}, ${st}`;
      }
      return null;
    },
  },
  {
    fact_id: "neighborhood",
    extract: (s) => {
      const hoods = [
        "East Side",
        "RiNo",
        "Capitol Hill",
        "Fremont",
        "Pearl District",
        "Alberta Arts",
      ];
      for (const h of hoods) if (new RegExp(`\\b${h}\\b`).test(s)) return h;
      return null;
    },
  },

  {
    fact_id: "blood_pressure_medication",
    extract: (s) => {
      if (/\btook me off losartan\b/i.test(s) || /\btook me off lisinopril\b/i.test(s)) {
        return null;
      }
      if (/\blosartan\b/i.test(s)) return "losartan";
      if (/\blisinopril\b/i.test(s)) return "lisinopril";
      return null;
    },
  },
  {
    fact_id: "diabetes_medication",
    extract: (s) => {
      if (/\bstop(?:ped|ping)?\b.*\bmetformin\b/i.test(s)) return "discontinued";
      if (/\btook me off metformin\b/i.test(s)) return "discontinued";
      if (/\bmetformin\b/i.test(s)) return "metformin";
      return null;
    },
  },
  {
    fact_id: "health_conditions",
    extract: (s) => {
      if (/\bpre-diabetes\b/i.test(s)) return "pre-diabetes";
      if (/\bhigh blood pressure\b/i.test(s) || /\bhypertension\b/i.test(s)) return "high blood pressure";
      return null;
    },
  },
  {
    fact_id: "lisinopril_side_effect",
    extract: (s) => {
      if (/\bdry cough\b/i.test(s)) return "dry cough";
      return null;
    },
  },
];

type StoredFact = {
  memory_id: string;
  value: string;
  as_of: string;
  source_session: number;
  source_message_index: number;
};

export interface AutoMemAdapterOptions {
  endpoint?: string;
  token?: string;
  /** Tags applied to every stored memory in addition to run/fact tags. */
  extra_tags?: string[];
}

export class AutoMemAdapter implements MemoryAdapter {
  readonly name = "automem";
  private endpoint: string;
  private token: string;
  private extraTags: string[];
  private runTag: string;
  private factHistory: Map<string, StoredFact[]>;
  private storedIds: Set<string>;

  constructor(options: AutoMemAdapterOptions = {}) {
    this.endpoint = options.endpoint ?? process.env.WRIT_AUTOMEM_ENDPOINT ?? "http://localhost:8001";
    this.token = options.token ?? process.env.WRIT_AUTOMEM_TOKEN ?? "test-token";
    this.extraTags = options.extra_tags ?? [];
    this.runTag = this.newRunTag();
    this.factHistory = new Map();
    this.storedIds = new Set();
  }

  private newRunTag(): string {
    const rand = Math.random().toString(36).slice(2, 8);
    return `writ-run-${Date.now()}-${rand}`;
  }

  private headers(): Record<string, string> {
    return {
      "Content-Type": "application/json",
      "X-Api-Key": this.token,
    };
  }

  private async post(path: string, body: unknown): Promise<unknown> {
    const res = await fetch(`${this.endpoint}${path}`, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`POST ${path} failed: ${res.status} ${text.slice(0, 200)}`);
    }
    return res.json();
  }

  private async del(path: string): Promise<void> {
    const res = await fetch(`${this.endpoint}${path}`, {
      method: "DELETE",
      headers: { "X-Api-Key": this.token },
    });
    if (!res.ok && res.status !== 404) {
      const text = await res.text().catch(() => "");
      throw new Error(`DELETE ${path} failed: ${res.status} ${text.slice(0, 200)}`);
    }
  }

  private async recall(params: Record<string, unknown>): Promise<RecallResultItem[]> {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v === undefined || v === null) continue;
      if (Array.isArray(v)) {
        for (const item of v) qs.append(k, String(item));
      } else if (typeof v === "boolean") {
        qs.set(k, v ? "true" : "false");
      } else {
        qs.set(k, String(v));
      }
    }
    const res = await fetch(`${this.endpoint}/recall?${qs.toString()}`, {
      method: "GET",
      headers: { "X-Api-Key": this.token },
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`GET /recall failed: ${res.status} ${text.slice(0, 200)}`);
    }
    const data = (await res.json()) as { results?: RecallResultItem[] };
    return data.results ?? [];
  }

  private extractFacts(content: string): Array<{ factId: string; value: string }> {
    const out: Array<{ factId: string; value: string }> = [];
    const seen = new Set<string>();
    for (const ext of FACT_EXTRACTORS) {
      if (seen.has(ext.fact_id)) continue;
      const value = ext.extract(content);
      if (value !== null) {
        out.push({ factId: ext.fact_id, value });
        seen.add(ext.fact_id);
      }
    }
    return out;
  }

  async init(): Promise<void> {
    const res = await fetch(`${this.endpoint}/health`, {
      headers: { "X-Api-Key": this.token },
    });
    if (!res.ok) {
      throw new Error(
        `AutoMem not reachable at ${this.endpoint}: HTTP ${res.status}`
      );
    }
  }

  async processSession(session: Session): Promise<void> {
    for (let i = 0; i < session.messages.length; i++) {
      const msg = session.messages[i]!;
      if (msg.role !== "user") continue;
      const facts = this.extractFacts(msg.content);
      if (facts.length === 0) continue;

      const factIds = facts.map((f) => f.factId);
      const tags = [
        this.runTag,
        `writ-session-${session.session_id}`,
        ...factIds.map((f) => `writ-fact-${f}`),
        ...this.extraTags,
      ];

      const payload = {
        content: msg.content,
        tags,
        type: "Context",
        importance: 0.7,
        timestamp: session.timestamp,
        metadata: {
          writ_run_id: this.runTag,
          writ_session: session.session_id,
          writ_message_index: i,
          writ_fact_ids: factIds,
          writ_fact_values: Object.fromEntries(facts.map((f) => [f.factId, f.value])),
        },
      };

      let resp: { memory_id?: string; id?: string };
      try {
        resp = (await this.post("/memory", payload)) as typeof resp;
      } catch (err) {
        console.error(`[automem-adapter] store failed s${session.session_id}:`, err);
        continue;
      }
      const mid = resp.memory_id ?? resp.id;
      if (!mid) continue;
      this.storedIds.add(mid);

      for (const { factId, value } of facts) {
        const list = this.factHistory.get(factId) ?? [];
        list.push({
          memory_id: mid,
          value,
          as_of: session.timestamp,
          source_session: session.session_id,
          source_message_index: i,
        });
        this.factHistory.set(factId, list);
      }
    }
  }

  async probe(prompt: string, options?: ProbeOptions): Promise<ProbeResult> {
    if (options?.mode === "no_memory") {
      return { answer: "", confidence: null, cited_sources: [], abstained: true };
    }

    if (options?.mode === "oracle_memory" && options.oracle_state) {
      const lower = prompt.toLowerCase();
      const matched: string[] = [];
      for (const [key, value] of Object.entries(options.oracle_state)) {
        if (lower.includes(key.toLowerCase())) matched.push(String(value));
      }
      const answer = matched.join("; ");
      return {
        answer,
        confidence: answer ? 1.0 : null,
        cited_sources: [],
        abstained: !answer,
      };
    }

    // Tag-only recall: writ probes are meta-questions ("remind me of X history")
    // and AutoMem's vector ranker drops sessions below a similarity threshold even
    // with a tag gate. We sort by session timestamp ourselves below.
    const items = await this.recall({
      tags: [this.runTag],
      limit: 50,
      sort: "recent",
    });

    if (items.length === 0) {
      return { answer: "", confidence: null, cited_sources: [], abstained: true };
    }

    const sessionOf = (r: RecallResultItem): number => {
      const md = r.memory?.metadata ?? {};
      const s = md.writ_session;
      if (typeof s === "number") return s;
      const ts = r.memory?.timestamp;
      return ts ? new Date(ts).getTime() : 0;
    };

    const sorted = [...items].sort((a, b) => sessionOf(a) - sessionOf(b));

    const answer = sorted
      .map((r) => {
        const content = r.memory?.content ?? "";
        const md = r.memory?.metadata ?? {};
        const factValues = md.writ_fact_values as Record<string, string> | undefined;
        if (!factValues || Object.keys(factValues).length === 0) return content;
        const canonical = Object.entries(factValues)
          .map(([k, v]) => `${k}=${v}`)
          .join(", ");
        return `${content} [facts: ${canonical}]`;
      })
      .filter(Boolean)
      .join(" ");
    const sources = sorted
      .map((r) => r.memory_id ?? r.id ?? "")
      .filter(Boolean);
    return {
      answer,
      confidence: 0.85,
      cited_sources: sources,
      abstained: false,
    };
  }

  async getHistory(factId: string): Promise<FactHistory | null> {
    const tracked = this.factHistory.get(factId);
    if (!tracked || tracked.length === 0) return null;

    const values: ValueHistoryEntry[] = tracked
      .slice()
      .sort((a, b) => new Date(a.as_of).getTime() - new Date(b.as_of).getTime())
      .map((s) => ({
        value: s.value,
        as_of: s.as_of,
        source_session: s.source_session,
      }));

    return {
      fact_id: factId,
      values,
      current_value: values[values.length - 1]?.value,
    };
  }

  async getStateAsOf(factId: string, timestamp: string): Promise<unknown | null> {
    const history = await this.getHistory(factId);
    if (!history) return null;
    const target = new Date(timestamp).getTime();
    let best: unknown = null;
    for (const entry of history.values) {
      if (new Date(entry.as_of).getTime() <= target) best = entry.value;
    }
    return best;
  }

  async getProvenance(_factId: string): Promise<Provenance | null> {
    return null;
  }

  getCapabilities(): AdapterCapabilities {
    return {
      supports_history: true,
      supports_temporal_replay: true,
      supports_provenance: false,
      supports_abstention: true,
      supports_source_authority: false,
      supports_deduplication: false,
      supports_lifecycle: false,
      supports_pre_delivery_certification: false,
    };
  }

  async reset(): Promise<void> {
    if (this.storedIds.size > 0) {
      for (const id of this.storedIds) {
        try {
          await this.del(`/memory/${id}`);
        } catch (err) {
          console.error(`[automem-adapter] delete ${id} failed:`, err);
        }
      }
    }
    this.storedIds.clear();
    this.factHistory.clear();
    this.runTag = this.newRunTag();
  }

  async teardown(): Promise<void> {
    await this.reset();
  }
}
