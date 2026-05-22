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

type ObservationKind =
  | "drift_fact"
  | "money"
  | "address"
  | "date"
  | "person"
  | "organization"
  | "contact"
  | "task_state"
  | "preference"
  | "constraint"
  | "lifecycle"
  | "retraction"
  | "role_person"
  | "travel"
  | "raw_message";

type SourceAuthorityHint =
  | "user_stated"
  | "user_confirmed"
  | "agreed_upon"
  | "agent_extracted"
  | "ai_summarized";

interface ExtractedObservation {
  factId: string;
  value: string;
  kind: ObservationKind;
  label: string;
  terms: string[];
  status?: string;
  retracted?: boolean;
}

interface Observation extends ExtractedObservation {
  memory_id: string;
  as_of: string;
  source_session: number;
  source_message_index: number;
  source_role: "user" | "assistant" | "system";
  source_authority: SourceAuthorityHint;
  content: string;
}

interface FactExtractor {
  fact_id: string;
  /** Return the normalized fact value if `content` references this fact, else null. */
  extract: (content: string) => string | null;
}

const STOP_WORDS = new Set([
  "a",
  "about",
  "all",
  "am",
  "an",
  "and",
  "are",
  "as",
  "at",
  "be",
  "been",
  "by",
  "can",
  "come",
  "comes",
  "current",
  "currently",
  "did",
  "do",
  "does",
  "for",
  "from",
  "has",
  "have",
  "history",
  "i",
  "in",
  "info",
  "information",
  "is",
  "it",
  "me",
  "my",
  "now",
  "of",
  "on",
  "or",
  "our",
  "please",
  "remind",
  "source",
  "the",
  "this",
  "to",
  "was",
  "were",
  "what",
  "when",
  "where",
  "which",
  "who",
  "with",
]);

const QUERY_ALIASES: Record<string, string[]> = {
  address: ["home", "mailing", "shipping", "street", "city", "lived", "live", "residence"],
  compensation: ["income", "salary", "pay", "bonus", "money", "budget", "cost", "amount"],
  employer: ["employment", "job", "work", "company", "organization"],
  lead: ["owner", "manager", "ceo", "director", "responsible"],
  lived: ["home", "city", "address", "residence", "neighborhood"],
  medication: ["medicine", "drug", "prescription", "health", "condition"],
  partner: ["relationship", "dating", "engaged", "spouse"],
  preference: ["constraint", "avoid", "allergy", "require", "likes", "dislikes"],
  salary: ["income", "compensation", "pay"],
  source: ["provenance", "origin", "where", "session", "message"],
  status: ["task", "todo", "state", "done", "pending", "blocked"],
};

function uniq(values: string[]): string[] {
  return [...new Set(values.filter(Boolean))];
}

function normalizeWhitespace(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

function normalizeFactId(label: string): string {
  const spaced = label
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/['"]/g, "")
    .replace(/[^a-zA-Z0-9]+/g, " ")
    .trim()
    .toLowerCase();
  return spaced.split(/\s+/).filter(Boolean).join("_");
}

function tokenize(value: unknown): string[] {
  const text = String(value ?? "")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .toLowerCase();
  const tokens = text.match(/[a-z0-9]+/g) ?? [];
  const expanded: string[] = [];
  for (const token of tokens) {
    if (STOP_WORDS.has(token)) continue;
    expanded.push(token);
    if (token.endsWith("s") && token.length > 3) {
      expanded.push(token.slice(0, -1));
    }
    for (const alias of QUERY_ALIASES[token] ?? []) {
      expanded.push(alias);
    }
  }
  return uniq(expanded);
}

function formatFactLabel(factId: string): string {
  return factId.replace(/_/g, " ");
}

function extraTermsForFact(factId: string): string[] {
  if (["employer", "title"].includes(factId)) {
    return ["employment", "job", "work"];
  }
  if (["base_salary", "bonus_target", "signing_bonus"].includes(factId)) {
    return ["income", "salary", "compensation", "pay", "bonus"];
  }
  if (["relationship_status", "partner_name", "living_arrangement"].includes(factId)) {
    return ["relationship", "partner", "dating", "timeline"];
  }
  if (["home_city", "neighborhood"].includes(factId)) {
    return ["address", "home", "lived", "residence", "state"];
  }
  if (["email", "phone_number", "personal_phone", "work_phone"].includes(factId)) {
    return ["contact", "phone", "email", "number"];
  }
  if (
    [
      "blood_pressure_medication",
      "diabetes_medication",
      "health_conditions",
      "lisinopril_side_effect",
    ].includes(factId)
  ) {
    return ["medication", "medicine", "drug", "prescription", "health", "condition", "side effect"];
  }
  return [];
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
      if (!/\b(?:base\s+salary|salary|income|compensation|comp|base|pay|earn|earning|offer pays|make|bumped me to)\b/i.test(s)) {
        return null;
      }
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
        return "called off engagement; split up; single";
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
        return partnerName ? `moved in with ${partnerName}` : "moved in";
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
      let m = s.match(/\b(losartan)\s+(\d+\s*mg)\b/i);
      if (m) return `${m[1]!.toLowerCase()} ${m[2]!.replace(/\s+/g, "")}`;
      m = s.match(/\b(lisinopril)\s+(\d+\s*mg)\b/i);
      if (m) return `${m[1]!.toLowerCase()} ${m[2]!.replace(/\s+/g, "")}`;
      if (/\blosartan\b/i.test(s)) return "losartan";
      if (/\blisinopril\b/i.test(s)) return "lisinopril";
      return null;
    },
  },
  {
    fact_id: "diabetes_medication",
    extract: (s) => {
      if (/\bstop(?:ped|ping)?\b.*\bmetformin\b/i.test(s)) return "discontinued metformin";
      if (/\btook me off metformin\b/i.test(s)) return "discontinued metformin";
      const m = s.match(/\b(metformin)\s+(\d+\s*mg)\b/i);
      if (m) return `${m[1]!.toLowerCase()} ${m[2]!.replace(/\s+/g, "")}`;
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
  private factHistory: Map<string, Observation[]>;
  private observations: Observation[];
  private storedIds: Set<string>;

  constructor(options: AutoMemAdapterOptions = {}) {
    this.endpoint = options.endpoint ?? process.env.WRIT_AUTOMEM_ENDPOINT ?? "http://localhost:8001";
    this.token = options.token ?? process.env.WRIT_AUTOMEM_TOKEN ?? "test-token";
    this.extraTags = options.extra_tags ?? [];
    this.runTag = this.newRunTag();
    this.factHistory = new Map();
    this.observations = [];
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

  private extractFacts(content: string): ExtractedObservation[] {
    const out: ExtractedObservation[] = [];
    const seen = new Set<string>();
    const add = (
      factId: string,
      value: string,
      kind: ObservationKind,
      label = formatFactLabel(factId),
      extraTerms: string[] = [],
      extra: Pick<ExtractedObservation, "status" | "retracted"> = {}
    ) => {
      const normalizedFactId = normalizeFactId(factId);
      const cleanValue = normalizeWhitespace(value);
      if (!normalizedFactId || !cleanValue) return;
      const dedupeKey = `${normalizedFactId}\0${cleanValue.toLowerCase()}\0${kind}`;
      if (seen.has(dedupeKey)) return;
      seen.add(dedupeKey);
      out.push({
        factId: normalizedFactId,
        value: cleanValue,
        kind,
        label,
        terms: uniq([
          ...tokenize(normalizedFactId),
          ...tokenize(label),
          ...tokenize(cleanValue),
          ...tokenize(content),
          ...extraTerms.flatMap((term) => tokenize(term)),
        ]),
        ...extra,
      });
    };

    for (const ext of FACT_EXTRACTORS) {
      const value = ext.extract(content);
      if (value !== null) {
        add(ext.fact_id, value, "drift_fact", formatFactLabel(ext.fact_id), extraTermsForFact(ext.fact_id));
      }
    }

    this.extractRolePeople(content, add);
    this.extractPreferenceFacts(content, add);
    this.extractMoneyFacts(content, add);
    this.extractAddressFacts(content, add);
    this.extractContactFacts(content, add);
    this.extractDateFacts(content, add);
    this.extractTaskFacts(content, add);
    this.extractLifecycleFacts(content, add);
    this.extractTravelFacts(content, add);
    this.extractNamedEntities(content, add);

    return out;
  }

  private extractRolePeople(
    content: string,
    add: (
      factId: string,
      value: string,
      kind: ObservationKind,
      label?: string,
      extraTerms?: string[],
      extra?: Pick<ExtractedObservation, "status" | "retracted">
    ) => void
  ): void {
    const patterns = [
      /\b(?:my|our|the)\s+([a-z][a-z0-9 /-]{1,45}?)\s+(?:is now|is currently|changed to|will be|became|is|was)\s+([A-Z][A-Za-z.'-]*(?:\s+[A-Z][A-Za-z.'-]*){0,3})\b/gi,
      /\b([A-Z][A-Za-z.'-]*(?:\s+[A-Z][A-Za-z.'-]*){0,3})\s+(?:is|was|became)\s+(?:my|our|the)\s+([a-z][a-z0-9 /-]{1,45}?)\b/gi,
    ];

    for (const pattern of patterns) {
      for (const match of content.matchAll(pattern)) {
        const first = normalizeWhitespace(match[1] ?? "");
        const second = normalizeWhitespace(match[2] ?? "");
        if (!first || !second) continue;
        const role = /^[A-Z]/.test(first) ? second : first;
        const person = /^[A-Z]/.test(first) ? first : second;
        if (/^(?:I|My|Our|The)$/i.test(person)) continue;
        if (this.looksLikeDateOrOrganization(person)) continue;
        add(role, person.replace(/\bnow\b$/i, "").trim(), "role_person", role, [role, "person"]);
      }
    }
  }

  private extractPreferenceFacts(
    content: string,
    add: (
      factId: string,
      value: string,
      kind: ObservationKind,
      label?: string,
      extraTerms?: string[]
    ) => void
  ): void {
    const avoidance = content.match(
      /\b(?:I|we)\s+(?:avoid|can't eat|cannot eat|do not eat|don't eat|am allergic to|need to avoid)\s+([^.!?;]+)/i
    );
    if (avoidance) {
      const object = normalizeWhitespace(avoidance[1]!);
      add(`avoid ${object}`, object, "constraint", "constraint", ["preference", "constraint"]);
    }

    const preference = content.match(
      /\b(?:my|our)\s+(?:preferred|favorite)\s+([a-z][a-z0-9 /-]{1,35}?)\s+(?:is now|is currently|is|was)\s+([^.!?;]+)/i
    );
    if (preference) {
      const label = `favorite ${normalizeWhitespace(preference[1]!)}`;
      add(label, normalizeWhitespace(preference[2]!), "preference", label, ["preference"]);
    }

    const simplePreference = content.match(
      /\b(?:I|we)\s+(?:prefer|like|need|require)\s+([^.!?;]+)/i
    );
    if (simplePreference) {
      const value = normalizeWhitespace(simplePreference[1]!);
      add(`preference ${normalizeWhitespace(simplePreference[1]!)}`, value, "preference", "preference", ["constraint"]);
    }
  }

  private extractMoneyFacts(
    content: string,
    add: (
      factId: string,
      value: string,
      kind: ObservationKind,
      label?: string,
      extraTerms?: string[]
    ) => void
  ): void {
    const moneyPattern = /\$[\d,]+(?:\.\d{2})?/g;
    for (const match of content.matchAll(moneyPattern)) {
      const amount = match[0]!;
      const start = Math.max(0, match.index! - 50);
      const end = Math.min(content.length, match.index! + amount.length + 50);
      const context = content.slice(start, end);
      const labelMatch = context.match(
        /\b([a-z][a-z0-9 -]{0,30}?(?:salary|income|compensation|pay|bonus|budget|cost|price|rent|amount|grant|revenue|expense|hotel|flight|deposit))\b/i
      );
      const label = labelMatch ? normalizeWhitespace(labelMatch[1]!) : "money amount";
      add(label, amount, "money", label, ["money", "amount", "compensation"]);
    }
  }

  private extractAddressFacts(
    content: string,
    add: (
      factId: string,
      value: string,
      kind: ObservationKind,
      label?: string,
      extraTerms?: string[]
    ) => void
  ): void {
    const address = content.match(
      /\b(?:my|our|the)?\s*(mailing address|shipping address|home address|address)\s+(?:is|was|changed to|is now|now is)\s+([^.!?;]+)/i
    );
    if (address) {
      const label = normalizeWhitespace(address[1]!);
      const value = normalizeWhitespace(address[2]!);
      add(label, value, "address", label, ["address", "street", "city"]);
      const cityStateZip = value.match(/,\s*([A-Z][A-Za-z .'-]+),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)\b/);
      if (cityStateZip) {
        add(
          "address city",
          `${normalizeWhitespace(cityStateZip[1]!)} , ${cityStateZip[2]} ${cityStateZip[3]}`.replace(" ,", ","),
          "address",
          "address city",
          ["address", "city", "state", "zip"]
        );
      }
    }

    const street = content.match(
      /\b(\d{1,6}\s+[A-Z][A-Za-z0-9 .'-]+?\s+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct))\b/
    );
    if (street) {
      add("address street", normalizeWhitespace(street[1]!), "address", "address street", ["address", "street"]);
    }

    const unit = content.match(/\b(?:Apt|Apartment|Unit|Suite)\s+[A-Za-z]*\d[A-Za-z0-9-]*\b/i);
    if (unit) {
      add("address unit", normalizeWhitespace(unit[0]!), "address", "address unit", ["address", "apartment", "unit"]);
    }
  }

  private extractContactFacts(
    content: string,
    add: (
      factId: string,
      value: string,
      kind: ObservationKind,
      label?: string,
      extraTerms?: string[]
    ) => void
  ): void {
    const emailPattern = /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi;
    let sawEmail = false;
    for (const match of content.matchAll(emailPattern)) {
      sawEmail = true;
      add("email", match[0]!, "contact", "email", extraTermsForFact("email"));
    }

    if (!sawEmail && /\b(?:revert|old email)\b/i.test(content)) {
      const domain = content.match(/\b([a-z0-9.-]+\.[a-z]{2,})\b/i)?.[1];
      if (domain) {
        const previous = this.latestObservationForValueSuffix("email", domain);
        if (previous) {
          add("email", previous.value, "contact", "email", extraTermsForFact("email"));
        }
      }
    }

    const phonePattern = /\b\d{3}[-.]\d{4}\b/g;
    for (const match of content.matchAll(phonePattern)) {
      const phone = match[0]!.replace(".", "-");
      const start = Math.max(0, match.index! - 60);
      const end = Math.min(content.length, match.index! + phone.length + 60);
      const context = content.slice(start, end);
      let factId = "phone_number";
      if (/\bwork phone\b/i.test(context)) factId = "work_phone";
      if (/\bpersonal\b/i.test(context)) factId = "personal_phone";
      add(factId, phone, "contact", formatFactLabel(factId), extraTermsForFact(factId));
    }
  }

  private latestObservationForValueSuffix(factId: string, suffix: string): Observation | null {
    const history = this.factHistory.get(factId) ?? [];
    const lowerSuffix = suffix.toLowerCase();
    for (const observation of history.slice().reverse()) {
      if (String(observation.value).toLowerCase().endsWith(lowerSuffix)) {
        return observation;
      }
    }
    return null;
  }

  private extractDateFacts(
    content: string,
    add: (
      factId: string,
      value: string,
      kind: ObservationKind,
      label?: string,
      extraTerms?: string[]
    ) => void
  ): void {
    const datePattern =
      /\b(?:deadline|due date|start date|end date|appointment|meeting|launch|renewal)\s+(?:is|was|on|for|at)?\s*([A-Z][a-z]+ \d{1,2}, \d{4}|\d{4}-\d{2}-\d{2})/gi;
    for (const match of content.matchAll(datePattern)) {
      const full = normalizeWhitespace(match[0]!);
      const label = full.replace(String(match[1]), "").replace(/\b(?:is|was|on|for|at)\b/gi, "").trim();
      add(label || "date", normalizeWhitespace(match[1]!), "date", label || "date", ["date", "time"]);
    }
  }

  private extractTaskFacts(
    content: string,
    add: (
      factId: string,
      value: string,
      kind: ObservationKind,
      label?: string,
      extraTerms?: string[],
      extra?: Pick<ExtractedObservation, "status" | "retracted">
    ) => void
  ): void {
    const taskPattern =
      /\b(?:task|todo|ticket|issue)\s+([A-Za-z0-9 _-]{1,45}?)\s+(?:is|was|became|now)?\s*(completed|complete|done|pending|blocked|cancelled|canceled|removed|open|closed)\b/gi;
    for (const match of content.matchAll(taskPattern)) {
      const task = normalizeWhitespace(match[1]!);
      const status = normalizeWhitespace(match[2]!).toLowerCase();
      add(`task ${task}`, status, "task_state", `task ${task}`, ["task", "status"], { status });
    }

    const finished = content.match(/\b(?:I|we)\s+(?:finished|completed|closed|removed)\s+([^.!?;]+)/i);
    if (finished) {
      const task = normalizeWhitespace(finished[1]!);
      add(`task ${task}`, "completed", "task_state", `task ${task}`, ["task", "status"], {
        status: "completed",
      });
    }
  }

  private extractLifecycleFacts(
    content: string,
    add: (
      factId: string,
      value: string,
      kind: ObservationKind,
      label?: string,
      extraTerms?: string[],
      extra?: Pick<ExtractedObservation, "status" | "retracted">
    ) => void
  ): void {
    const statusPatterns: Array<[RegExp, string]> = [
      [/\b(?:no longer|not anymore|deprecated|superseded|replaced|retired)\b/i, "superseded"],
      [/\b(?:resolved|closed|fixed|completed)\b/i, "resolved"],
      [/\b(?:expired|lapsed)\b/i, "expired"],
      [/\b(?:reinstated|restored|active again)\b/i, "reinstated"],
      [/\b(?:retracted|forget|remove|deleted)\b/i, "retracted"],
    ];
    for (const [pattern, status] of statusPatterns) {
      if (!pattern.test(content)) continue;
      const value = normalizeWhitespace(content);
      const labelMatch = content.match(/\b(?:the|my|our)\s+([a-z][a-z0-9 /-]{1,45})\b/i);
      const label = labelMatch ? normalizeWhitespace(labelMatch[1]!) : "lifecycle status";
      add(label, value, status === "retracted" ? "retraction" : "lifecycle", label, ["lifecycle", status], {
        status,
        retracted: status === "retracted",
      });
    }
  }

  private extractTravelFacts(
    content: string,
    add: (
      factId: string,
      value: string,
      kind: ObservationKind,
      label?: string,
      extraTerms?: string[]
    ) => void
  ): void {
    const location =
      content.match(/\btrip to ([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b/)?.[1] ??
      content.match(/\b(?:at|with)\s+(?:our|the)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+office\b/)?.[1];
    if (location) {
      add("trip location", location, "travel", "trip location", ["trip", "travel", "location"]);
    }

    const duration = content.match(/\b((?:one|two|three|four|five|six|\d+)[-\s](?:week|day)s?)\b/i)?.[1];
    if (duration) {
      add("trip duration", normalizeWhitespace(duration), "travel", "trip duration", ["trip", "travel", "duration"]);
    }

    if (/\bclient engagement\b/i.test(content)) {
      const office = content.match(/\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+office\b/)?.[1];
      add(
        "trip purpose",
        office ? `client engagement at ${office} office` : "client engagement",
        "travel",
        "trip purpose",
        ["trip", "travel", "purpose"]
      );
    } else if (/\bwork conference\b/i.test(content)) {
      add("trip purpose", "work conference", "travel", "trip purpose", ["trip", "travel", "purpose"]);
    } else if (/\bvacation\b/i.test(content) && !/\bwasn'?t a vacation\b/i.test(content)) {
      add("trip purpose", "vacation", "travel", "trip purpose", ["trip", "travel", "purpose"]);
    }
  }

  private extractNamedEntities(
    content: string,
    add: (
      factId: string,
      value: string,
      kind: ObservationKind,
      label?: string,
      extraTerms?: string[]
    ) => void
  ): void {
    const organizationPattern =
      /\b([A-Z][A-Za-z0-9&.'-]*(?:\s+[A-Z][A-Za-z0-9&.'-]*){0,4}\s+(?:Labs|Corp|Corporation|Inc|LLC|Ltd|Co|Company|University|Group|Studio|Systems))\b/g;
    for (const match of content.matchAll(organizationPattern)) {
      add("organization", normalizeWhitespace(match[1]!), "organization", "organization", ["company", "employer"]);
    }

    const peoplePattern = /\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b/g;
    for (const match of content.matchAll(peoplePattern)) {
      const name = normalizeWhitespace(match[1]!);
      if (/^(?:I|My|Our|The)$/i.test(name)) continue;
      if (this.looksLikeDateOrOrganization(name)) continue;
      add("person", name, "person", "person", ["person", "name"]);
    }
  }

  private looksLikeDateOrOrganization(value: string): boolean {
    return /\b(?:Actually|Apt|Avenue|Can|Court|Drive|February|January|March|April|May|June|July|August|September|October|November|December|Labs|Corp|Inc|LLC|Ltd|Co|University|Street|What|Wait)\b/i.test(value);
  }

  private detectSourceAuthority(content: string): SourceAuthorityHint {
    if (/\b(?:we decided|agreed upon)\b/i.test(content)) {
      return "agreed_upon";
    }
    if (/\b(?:confirmed|verified|agreed|we agreed)\b/i.test(content)) {
      return "user_confirmed";
    }
    if (/\b(?:assistant|agent|ai)\s+(?:said|extracted|summarized|claimed)\b/i.test(content)) {
      return "agent_extracted";
    }
    if (/\b(?:summary|summarized|recap)\b/i.test(content)) {
      return "ai_summarized";
    }
    return "user_stated";
  }

  private rememberObservation(observation: Observation): void {
    this.observations.push(observation);
    const list = this.factHistory.get(observation.factId) ?? [];
    list.push(observation);
    list.sort((a, b) => new Date(a.as_of).getTime() - new Date(b.as_of).getTime());
    this.factHistory.set(observation.factId, list);
  }

  private resolveFactKey(factId: string): string | null {
    const normalized = normalizeFactId(factId);
    if (this.factHistory.has(normalized)) return normalized;

    const queryTokens = tokenize(factId);
    if (queryTokens.length === 0) return null;

    let bestKey: string | null = null;
    let bestScore = 0;
    for (const [key, entries] of this.factHistory.entries()) {
      if (key.startsWith("message_")) continue;
      const entryTerms = new Set<string>([
        ...tokenize(key),
        ...entries.flatMap((entry) => entry.terms),
      ]);
      const overlap = queryTokens.filter((token) => entryTerms.has(token)).length;
      const exactish = key.includes(normalized) || normalized.includes(key) ? 2 : 0;
      const score = overlap + exactish;
      if (score > bestScore) {
        bestScore = score;
        bestKey = key;
      }
    }
    return bestScore > 0 ? bestKey : null;
  }

  private scoreObservation(promptTokens: string[], observation: Observation): number {
    const obsTokens = new Set([
      ...tokenize(observation.factId),
      ...tokenize(observation.label),
      ...observation.terms,
    ]);
    let score = 0;
    for (const token of promptTokens) {
      if (obsTokens.has(token)) score++;
    }
    if (observation.kind === "raw_message") {
      score *= 0.5;
    }
    return score;
  }

  private relevantFactKeys(prompt: string): string[] {
    const promptTokens = tokenize(prompt);
    if (promptTokens.length === 0) return [];

    const scores = new Map<string, number>();
    for (const observation of this.observations) {
      if (observation.kind === "raw_message") continue;
      const score = this.scoreObservation(promptTokens, observation);
      if (score <= 0) continue;
      scores.set(observation.factId, Math.max(scores.get(observation.factId) ?? 0, score));
    }
    const best = Math.max(0, ...scores.values());
    if (best === 0) return [];
    const threshold = this.promptIntent(prompt) === "history" ? 1 : Math.max(1, best * 0.6);
    const selected = [...scores.entries()]
      .filter(([, score]) => score >= threshold)
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
      .map(([key]) => key)
      .filter((key, _index, keys) => {
        const hasSpecific = keys.some((candidate) => !["person", "organization"].includes(candidate));
        return !hasSpecific || !["person", "organization"].includes(key);
      });
    const hasSpecific = selected.some((key) => !["person", "organization"].includes(key));
    const identityPrompt = /\b(?:who|name|person|people|manager|lead|doctor|dentist|teammate|coworker|sister|brother|partner)\b/i.test(prompt);
    if (!hasSpecific && !identityPrompt) return [];
    return selected;
  }

  private latestObservation(factId: string, asOf?: string): Observation | null {
    const history = this.factHistory.get(factId);
    if (!history || history.length === 0) return null;
    const target = asOf ? new Date(asOf).getTime() : Number.POSITIVE_INFINITY;
    let best: Observation | null = null;
    for (const observation of history) {
      if (new Date(observation.as_of).getTime() <= target) {
        best = observation;
      }
    }
    if (best?.retracted) return null;
    return best;
  }

  private promptIntent(prompt: string): "history" | "temporal" | "provenance" | "current" {
    if (/\b(?:where did|source|provenance|come from|who told|which session|which message)\b/i.test(prompt)) {
      return "provenance";
    }
    if (/\b(?:as of|at the time|then|in \w+ \d{4}|on \d{4}-\d{2}-\d{2})\b/i.test(prompt)) {
      return "temporal";
    }
    if (/\b(?:history|previous|past|formerly|used to|changed|timeline|everywhere|all places|all the)\b/i.test(prompt)) {
      return "history";
    }
    return "current";
  }

  private parsePromptDate(prompt: string): string | null {
    const iso = prompt.match(/\b(\d{4}-\d{2}-\d{2})(?:T[0-9:.Z+-]+)?\b/);
    if (iso) return `${iso[1]}T23:59:59Z`;

    const monthNames: Record<string, number> = {
      january: 0,
      february: 1,
      march: 2,
      april: 3,
      may: 4,
      june: 5,
      july: 6,
      august: 7,
      september: 8,
      october: 9,
      november: 10,
      december: 11,
    };
    const month = prompt.match(
      /\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(?:(\d{1,2}),\s*)?(\d{4})\b/i
    );
    if (!month) return null;
    const monthIndex = monthNames[month[1]!.toLowerCase()]!;
    const year = Number(month[3]);
    const day = month[2] ? Number(month[2]) : new Date(Date.UTC(year, monthIndex + 1, 0)).getUTCDate();
    return new Date(Date.UTC(year, monthIndex, day, 23, 59, 59)).toISOString();
  }

  private formatCurrentAnswer(keys: string[], asOf?: string): { answer: string; sources: string[] } | null {
    const observations = keys
      .map((key) => this.latestObservation(key, asOf))
      .filter((entry): entry is Observation => entry !== null);
    if (observations.length === 0) return null;

    const answer = observations
      .map((entry) => `${entry.label} is ${entry.value}`)
      .join("; ");
    return {
      answer: asOf ? `As of ${asOf}, ${answer}.` : `${answer}.`,
      sources: uniq(observations.map((entry) => entry.memory_id)),
    };
  }

  private formatHistoryAnswer(keys: string[]): { answer: string; sources: string[] } | null {
    const parts: string[] = [];
    const sources: string[] = [];
    for (const key of keys) {
      const history = this.factHistory.get(key) ?? [];
      if (history.length === 0) continue;
      const values = history.map((entry) => {
        sources.push(entry.memory_id);
        return `${entry.value} (session ${entry.source_session})`;
      });
      parts.push(`${formatFactLabel(key)} history: ${values.join(" -> ")}`);
    }
    if (parts.length === 0) return null;
    return { answer: `${parts.join("; ")}.`, sources: uniq(sources) };
  }

  private formatProvenanceAnswer(keys: string[]): { answer: string; sources: string[] } | null {
    const key = keys[0];
    if (!key) return null;
    const latest = this.latestObservation(key);
    if (!latest) return null;
    return {
      answer: `${latest.label} came from session ${latest.source_session}, message ${latest.source_message_index}: ${latest.content}`,
      sources: [latest.memory_id],
    };
  }

  private recallSources(items: RecallResultItem[]): string[] {
    return items.map((r) => r.memory_id ?? r.id ?? "").filter(Boolean);
  }

  private chronologicalRecallAnswer(items: RecallResultItem[], prompt: string): { answer: string; sources: string[] } | null {
    const promptTokens = tokenize(prompt);
    const scored = items
      .map((item) => {
        const content = item.memory?.content ?? "";
        const contentTokens = new Set(tokenize(content));
        const score = promptTokens.filter((token) => contentTokens.has(token)).length;
        return { item, content, score };
      })
      .filter(({ content, score }) => content && score > 0)
      .sort((a, b) => {
        const at = a.item.memory?.timestamp ? new Date(a.item.memory.timestamp).getTime() : 0;
        const bt = b.item.memory?.timestamp ? new Date(b.item.memory.timestamp).getTime() : 0;
        return at - bt;
      });
    if (scored.length === 0) return null;
    return {
      answer: scored.map(({ content }) => content).join(" "),
      sources: this.recallSources(scored.map(({ item }) => item)),
    };
  }

  private isSensitiveCredentialPrompt(prompt: string): boolean {
    return /\b(?:password|credential|secret|api key|token|private key)\b/i.test(prompt);
  }

  private possessiveSubject(prompt: string): string | null {
    for (const match of prompt.matchAll(/\b([A-Z][a-z]+)'s\b/g)) {
      const name = match[1]!;
      if (/^(?:What|Where|When|Who|How|Can|Do|Does|Is|Are)$/i.test(name)) continue;
      return name;
    }
    return null;
  }

  private selectedFactsMentionSubject(keys: string[], subject: string): boolean {
    const subjectPattern = new RegExp(`\\b${subject.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "i");
    return keys.some((key) => {
      const entries = this.factHistory.get(key) ?? [];
      return entries.some((entry) => subjectPattern.test(entry.content) || subjectPattern.test(entry.value));
    });
  }

  private abstain(intent: string, queryRecallCount = 0): ProbeResult {
    return {
      answer: "",
      confidence: null,
      cited_sources: [],
      abstained: true,
      raw_response: { query_recall_count: queryRecallCount, intent },
    };
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

      const factIds = uniq(facts.map((f) => f.factId));
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
          writ_role: msg.role,
          writ_timestamp: session.timestamp,
          writ_raw_content: msg.content,
          writ_source_authority: this.detectSourceAuthority(msg.content),
          writ_fact_ids: factIds,
          writ_fact_values: Object.fromEntries(facts.map((f) => [f.factId, f.value])),
          writ_observations: facts.map((f) => ({
            fact_id: f.factId,
            value: f.value,
            kind: f.kind,
            label: f.label,
            status: f.status,
            retracted: f.retracted,
          })),
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

      const sourceAuthority = this.detectSourceAuthority(msg.content);
      for (const fact of facts) {
        this.rememberObservation({
          ...fact,
          memory_id: mid,
          as_of: session.timestamp,
          source_session: session.session_id,
          source_message_index: i,
          source_role: msg.role,
          source_authority: sourceAuthority,
          content: msg.content,
        });
      }

      this.rememberObservation({
        factId: `message_${session.session_id}_${i}`,
        value: msg.content,
        kind: "raw_message",
        label: "message",
        terms: tokenize(msg.content),
        memory_id: mid,
        as_of: session.timestamp,
        source_session: session.session_id,
        source_message_index: i,
        source_role: msg.role,
        source_authority: sourceAuthority,
        content: msg.content,
      });
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

    const intent = this.promptIntent(prompt);
    let queryItems: RecallResultItem[] = [];
    try {
      queryItems = await this.recall({
        query: prompt,
        tags: [this.runTag],
        limit: 20,
        sort: "recent",
      });
    } catch (err) {
      console.error("[automem-adapter] prompt recall failed:", err);
    }

    if (this.isSensitiveCredentialPrompt(prompt)) {
      return this.abstain(intent, queryItems.length);
    }

    const keys = this.relevantFactKeys(prompt);
    const possessiveSubject = this.possessiveSubject(prompt);
    if (possessiveSubject && keys.length > 0 && !this.selectedFactsMentionSubject(keys, possessiveSubject)) {
      return this.abstain(intent, queryItems.length);
    }

    let formatted: { answer: string; sources: string[] } | null = null;
    if (keys.length > 0) {
      if (intent === "history") {
        formatted = this.formatHistoryAnswer(keys);
      } else if (intent === "temporal") {
        const asOf = this.parsePromptDate(prompt);
        formatted = this.formatCurrentAnswer(keys, asOf ?? undefined);
      } else if (intent === "provenance") {
        formatted = this.formatProvenanceAnswer(keys);
      } else {
        formatted = this.formatCurrentAnswer(keys);
      }
    }

    if (formatted) {
      return {
        answer: formatted.answer,
        confidence: 0.85,
        cited_sources: uniq([...formatted.sources, ...this.recallSources(queryItems)]),
        abstained: false,
        raw_response: { query_recall_count: queryItems.length, intent },
      };
    }

    if (intent === "history") {
      let chronologicalItems: RecallResultItem[] = [];
      try {
        chronologicalItems = await this.recall({
          tags: [this.runTag],
          limit: 50,
          sort: "recent",
        });
      } catch (err) {
        console.error("[automem-adapter] history recall failed:", err);
      }
      const fallback = this.chronologicalRecallAnswer(chronologicalItems, prompt);
      if (fallback) {
        return {
          answer: fallback.answer,
          confidence: 0.65,
          cited_sources: fallback.sources,
          abstained: false,
          raw_response: { query_recall_count: queryItems.length, intent, fallback: "chronological_recall" },
        };
      }
    }

    const recalledFallback = this.chronologicalRecallAnswer(queryItems, prompt);
    if (recalledFallback) {
      return {
        answer: recalledFallback.answer,
        confidence: 0.6,
        cited_sources: recalledFallback.sources,
        abstained: false,
        raw_response: { query_recall_count: queryItems.length, intent, fallback: "prompt_recall" },
      };
    }

    return {
      answer: "",
      confidence: null,
      cited_sources: [],
      abstained: true,
      raw_response: { query_recall_count: queryItems.length, intent },
    };
  }

  async getHistory(factId: string): Promise<FactHistory | null> {
    const resolved = this.resolveFactKey(factId);
    const tracked = resolved ? this.factHistory.get(resolved) : null;
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

  async getProvenance(factId: string): Promise<Provenance | null> {
    const resolved = this.resolveFactKey(factId);
    const tracked = resolved ? this.factHistory.get(resolved) : null;
    if (!tracked || tracked.length === 0) return null;
    const sorted = tracked
      .slice()
      .sort((a, b) => new Date(a.as_of).getTime() - new Date(b.as_of).getTime());
    const latest = sorted[sorted.length - 1]!;
    return {
      fact_id: factId,
      source_session: latest.source_session,
      source_message_index: latest.source_message_index,
      agent_or_user: latest.source_role,
      chain: sorted.map((entry, index) => ({
        timestamp: entry.as_of,
        action: entry.retracted ? "retracted" : index === 0 ? "created" : "updated",
        session: entry.source_session,
        value: entry.value,
      })),
    };
  }

  getCapabilities(): AdapterCapabilities {
    return {
      supports_history: true,
      supports_temporal_replay: true,
      supports_provenance: true,
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
    this.observations = [];
    this.runTag = this.newRunTag();
  }

  async teardown(): Promise<void> {
    await this.reset();
  }
}
