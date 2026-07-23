import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { buildRuleProposals } from "./rule_proposals.ts";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL") ?? "";
const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
const FEEDBACK_FORM_URL = Deno.env.get("FEEDBACK_FORM_URL") ?? "";

const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);

type FeedbackType = "good" | "not_good";
type FeedbackRow = {
  post_id: string;
  post_url: string | null;
  title: string | null;
  feedback_type: FeedbackType;
  note: string | null;
  feedback_category: string | null;
  positive_signal_category: string | null;
  extracted_title_keywords: string[] | null;
  extracted_location_terms: string[] | null;
  extracted_domain_terms: string[] | null;
  extracted_seniority_terms: string[] | null;
  created_at: string;
};

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
};

function text(body: string, status = 200): Response {
  return new Response(body, {
    status,
    headers: { ...corsHeaders, "Content-Type": "text/plain; charset=utf-8" },
  });
}

function json(body: Record<string, unknown>, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders, "Content-Type": "application/json; charset=utf-8" },
  });
}

function html(body: string, status = 200): Response {
  return new Response(body, {
    status,
    headers: { ...corsHeaders, "Content-Type": "text/html; charset=utf-8" },
  });
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function countValues(values: string[]): Record<string, number> {
  return values.reduce((acc: Record<string, number>, value) => {
    acc[value] = (acc[value] ?? 0) + 1;
    return acc;
  }, {});
}

function mostCommon(values: string[], limit = 20): Array<[string, number]> {
  return Object.entries(countValues(values))
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, limit);
}

function unique(values: string[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const value of values) {
    if (!value || seen.has(value.toLowerCase())) continue;
    seen.add(value.toLowerCase());
    result.push(value);
  }
  return result;
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function normalizedText(text: string): string {
  return text.toLowerCase().replace(/\bu\.s\./g, "us");
}

function hasTerm(text: string, term: string): boolean {
  const lower = normalizedText(text);
  const termLower = normalizedText(term);
  if (termLower.length <= 3 || /^[a-z0-9.]+$/i.test(term)) {
    return new RegExp(`\\b${escapeRegExp(termLower)}\\b`, "i").test(lower);
  }
  return lower.includes(termLower);
}

function containsAny(text: string, terms: string[]): string[] {
  return terms.filter((term) => hasTerm(text, term));
}

function locationTerms(text: string): string[] {
  const lower = normalizedText(text);
  const negatedAllowedLocation =
    /\bnot\s+in(?:\s+the)?\s+(?:us|u\.s\.|ny|sf|new york|san francisco)\b/.test(lower);
  return LOCATION_TERMS.filter((term) => {
    const termLower = normalizedText(term);
    if (
      negatedAllowedLocation &&
      ["us", "sf", "new york", "nyc", "san francisco"].includes(termLower)
    ) {
      return false;
    }
    return hasTerm(text, term);
  });
}

function classifyNotGood(note = ""): string {
  const lower = normalizedText(note);
  if (["no longer exist", "no longer exists", "expired", "broken link"].some((term) => lower.includes(term))) return "expired_post";
  if (lower.includes("not a hiring post")) return "not_hiring_post";
  if (/\b(senior|principal|staff|lead|director)\b/.test(lower)) return "too_senior";
  if (/\b(10\s*\+?\s*years?|8\s*\+?\s*years?)\b/.test(lower)) return "too_senior";
  if (["not in us", "not in the us", "not in ny", "not in sf", "uk", "canada", "india", "europe", "mumbai", "london", "texas"].some((term) => hasTerm(lower, term))) {
    return "wrong_location";
  }
  if (lower.includes("duplicate")) return "duplicate";
  if (["wrong domain", "not relevant domain", "irrelevant domain"].some((term) => lower.includes(term))) return "not_relevant_domain";
  return "not_relevant_domain";
}

const ROLE_ARCHETYPES = [
  "AI Automation Engineer",
  "AI Agent Engineer",
  "AI Solutions Consultant",
  "AI Solutions Engineer",
  "AI Enablement",
  "AI Builder",
  "Applied AI Engineer",
  "Forward Deployed AI Engineer",
  "TA Operations",
  "Technical Product Manager",
  "AI Product Manager",
  "Data Scientist",
  "ML Engineer",
  "Analytics Engineer",
];
const AI_AGENT_TERMS = ["AI Agent", "AI Agents", "agentic AI", "agentic", "multi-agent", "LLM agent", "RAG", "tool calling", "function calling"];
const WORKFLOW_TERMS = ["workflow", "workflow automation", "automation", "operations automation", "process automation", "internal tools", "internal enablement", "n8n", "Zapier", "Gumloop", "Power Automate"];
const GTM_TERMS = ["GTM", "go-to-market", "sales enablement", "revops", "revenue operations", "marketing automation", "customer intelligence"];
const DOMAIN_TERMS = ["agentic AI", "AI Agent", "AI agents", "LLM", "RAG", "workflow automation", "operations automation", "internal enablement", "GTM automation", "healthcare", "healthtech", "clinical", "claims", "life sciences", "data products", "productivity tooling"];
const LOCATION_TERMS = ["Remote US", "US Remote", "United States", "US", "New York", "NYC", "San Francisco", "SF", "Bay Area", "California", "Texas", "UK", "United Kingdom", "Canada", "India", "Europe", "Mumbai", "London"];
const SENIORITY_TERMS = ["intern", "entry", "entry-level", "junior", "associate", "early career", "mid-level", "mid level", "senior", "staff", "principal", "lead", "director", "head of", "vp", "10+ years", "8+ years"];
const STOPWORDS = new Set(["a", "an", "and", "at", "for", "in", "of", "on", "or", "role", "the", "to", "with", "remote", "hybrid", "onsite", "specialist", "manager", "engineer"]);

function titleKeywords(title = ""): string[] {
  const archetypes = containsAny(title, ROLE_ARCHETYPES);
  const words = Array.from(title.matchAll(/[A-Za-z][A-Za-z0-9+.-]{2,}/g))
    .map((match) => match[0])
    .filter((word) => !STOPWORDS.has(word.toLowerCase()) && !/^\d+$/.test(word));
  return unique([...archetypes, ...words]).slice(0, 12);
}

function classifyPositive(title = "", note = ""): string {
  const text = `${title} ${note}`.toLowerCase();
  if (AI_AGENT_TERMS.some((term) => text.includes(term.toLowerCase()))) return "strong_ai_agent_match";
  if (WORKFLOW_TERMS.some((term) => text.includes(term.toLowerCase()))) return "strong_workflow_automation_match";
  if (GTM_TERMS.some((term) => text.includes(term.toLowerCase()))) return "strong_gtm_ai_match";
  if (ROLE_ARCHETYPES.some((term) => text.includes(term.toLowerCase()))) return "strong_role_match";
  if (["healthcare", "healthtech", "clinical", "claims", "life sciences"].some((term) => text.includes(term))) return "strong_domain_match";
  if (["remote us", "us remote", "new york", "san francisco", "bay area"].some((term) => text.includes(term))) return "strong_location_match";
  if (["associate", "junior", "entry", "early career", "mid-level", "mid level", "senior"].some((term) => text.includes(term))) return "acceptable_seniority";
  return "other";
}

function structureFeedback(feedback_type: FeedbackType, title = "", note = ""): Record<string, unknown> {
  const text = `${title} ${note}`;
  const domainTerms = containsAny(text, [...DOMAIN_TERMS, ...AI_AGENT_TERMS, ...WORKFLOW_TERMS, ...GTM_TERMS]);
  if (text.toLowerCase().includes("ai agent") && text.toLowerCase().includes("operations")) {
    domainTerms.push("operations automation");
  }
  return {
    feedback_category: feedback_type === "not_good" ? classifyNotGood(note) : null,
    positive_signal_category: feedback_type === "good" ? classifyPositive(title, note) : null,
    extracted_title_keywords: titleKeywords(title),
    extracted_location_terms: locationTerms(text),
    extracted_domain_terms: unique(domainTerms),
    extracted_seniority_terms: containsAny(text, SENIORITY_TERMS),
  };
}

function feedbackFormUrl(apiUrl: URL, feedbackType: FeedbackType = "not_good"): string {
  const formUrl = new URL(FEEDBACK_FORM_URL);
  for (const key of ["post_id", "post_url", "title"]) {
    const value = apiUrl.searchParams.get(key);
    if (value) {
      formUrl.searchParams.set(key, value);
    }
  }
  formUrl.searchParams.set(
    "api_url",
    `${SUPABASE_URL.replace(/\/$/, "")}/functions/v1/role-feedback`,
  );
  formUrl.searchParams.set("feedback_type", feedbackType);
  return formUrl.toString();
}

function goodConfirmationPage(apiUrl: URL): Response {
  if (!FEEDBACK_FORM_URL) {
    return text("Feedback form URL is not configured", 500);
  }
  return Response.redirect(feedbackFormUrl(apiUrl, "good"), 303);
}

type SaveFeedbackResult = {
  ok: boolean;
  status: "saved" | "duplicate_ignored" | "conflict_ignored" | "error";
  message: string;
  httpStatus: number;
};

async function saveFeedback(payload: {
  post_id: string;
  post_url: string;
  title: string;
  feedback_type: FeedbackType;
  note?: string;
}): Promise<SaveFeedbackResult> {
  const { data: existingRows, error: lookupError } = await supabase
    .from("role_feedback")
    .select("id,feedback_type,created_at")
    .eq("post_id", payload.post_id)
    .order("created_at", { ascending: false });

  if (lookupError) {
    console.error("Failed to check existing role feedback", lookupError);
    return {
      ok: false,
      status: "error",
      message: "Could not check existing feedback",
      httpStatus: 500,
    };
  }

  const existing = existingRows ?? [];
  if (existing.some((row) => row.feedback_type === payload.feedback_type)) {
    return {
      ok: true,
      status: "duplicate_ignored",
      message: `Feedback already saved as ${payload.feedback_type}`,
      httpStatus: 200,
    };
  }

  const hasNotGood = existing.some((row) => row.feedback_type === "not_good");
  if (payload.feedback_type === "good" && hasNotGood) {
    return {
      ok: true,
      status: "conflict_ignored",
      message: "Not saved: this post already has not-good feedback",
      httpStatus: 200,
    };
  }

  if (payload.feedback_type === "not_good") {
    const { error: deleteError } = await supabase
      .from("role_feedback")
      .delete()
      .eq("post_id", payload.post_id)
      .eq("feedback_type", "good");
    if (deleteError) {
      console.error("Failed to remove stale good feedback", deleteError);
      return {
        ok: false,
        status: "error",
        message: "Could not replace stale good feedback",
        httpStatus: 500,
      };
    }
  }

  const structured = structureFeedback(payload.feedback_type, payload.title, payload.note ?? "");
  const { error } = await supabase.from("role_feedback").insert({ ...payload, ...structured });
  if (error) {
    if (error.code === "23505") {
      return {
        ok: true,
        status: "duplicate_ignored",
        message: `Feedback already saved as ${payload.feedback_type}`,
        httpStatus: 200,
      };
    }
    console.error("Failed to save role feedback", error);
    return { ok: false, status: "error", message: "Could not save feedback", httpStatus: 500 };
  }

  return { ok: true, status: "saved", message: "Feedback saved", httpStatus: 200 };
}

function feedbackResponse(result: SaveFeedbackResult, wantsHtml: boolean): Response {
  if (wantsHtml) {
    const heading = result.ok ? "Feedback saved" : "Feedback not saved";
    return html(`<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${escapeHtml(heading)}</title>
<style>
  body{font-family:system-ui,sans-serif;max-width:640px;margin:40px auto;padding:0 16px;color:#222}
  h1{font-size:1.35rem;margin:0 0 8px}
  p{color:#666}
</style>
</head>
<body>
<h1>${escapeHtml(heading)}</h1>
<p>${escapeHtml(result.message)}</p>
</body>
</html>`, result.httpStatus);
  }

  if (!result.ok) {
    return json({ ok: false, status: result.status, error: result.message }, result.httpStatus);
  }
  return json({ ok: true, status: result.status, message: result.message }, result.httpStatus);
}

async function loadFeedbackRows(): Promise<FeedbackRow[]> {
  const { data, error } = await supabase
    .from("role_feedback")
    .select("*")
    .order("created_at", { ascending: false });
  if (error) throw error;
  return (data ?? []) as FeedbackRow[];
}

function enriched(row: FeedbackRow): FeedbackRow {
  const structured = structureFeedback(row.feedback_type, row.title ?? "", row.note ?? "");
  return {
    ...row,
    feedback_category: row.feedback_category ?? structured.feedback_category as string | null,
    positive_signal_category: row.positive_signal_category ?? structured.positive_signal_category as string | null,
    extracted_title_keywords: row.extracted_title_keywords ?? structured.extracted_title_keywords as string[],
    extracted_location_terms: row.extracted_location_terms ?? structured.extracted_location_terms as string[],
    extracted_domain_terms: row.extracted_domain_terms ?? structured.extracted_domain_terms as string[],
    extracted_seniority_terms: row.extracted_seniority_terms ?? structured.extracted_seniority_terms as string[],
  };
}

function preferenceProfile(rows: FeedbackRow[]): Record<string, unknown> {
  const good = rows.filter((row) => row.feedback_type === "good");
  const bad = rows.filter((row) => row.feedback_type === "not_good");
  return {
    preferred_role_title_patterns: mostCommon(good.flatMap((row) => row.extracted_title_keywords ?? [])).map(([value]) => value),
    preferred_domain_keywords: mostCommon(good.flatMap((row) => row.extracted_domain_terms ?? [])).map(([value]) => value),
    preferred_workflow_automation_keywords: mostCommon(good.flatMap((row) => row.extracted_domain_terms ?? []).filter((value) => /workflow|automation/i.test(value))).map(([value]) => value),
    preferred_ai_agent_keywords: mostCommon(good.flatMap((row) => row.extracted_domain_terms ?? []).filter((value) => /agent|agentic|llm|rag/i.test(value))).map(([value]) => value),
    preferred_location_patterns: mostCommon(good.flatMap((row) => row.extracted_location_terms ?? [])).map(([value]) => value),
    acceptable_seniority_patterns: mostCommon(good.flatMap((row) => row.extracted_seniority_terms ?? [])).map(([value]) => value),
    rejected_title_patterns: mostCommon(bad.flatMap((row) => row.extracted_title_keywords ?? [])).map(([value]) => value),
    rejected_location_patterns: mostCommon(bad.flatMap((row) => row.extracted_location_terms ?? [])).map(([value]) => value),
    rejected_seniority_patterns: mostCommon(bad.flatMap((row) => row.extracted_seniority_terms ?? [])).map(([value]) => value),
    examples_of_good_matches: good.slice(0, 8).map((row) => ({ title: row.title, post_url: row.post_url })),
    examples_of_bad_matches: bad.slice(0, 8).map((row) => ({ title: row.title, post_url: row.post_url, reason: row.feedback_category })),
  };
}

function ruleProposals(rows: FeedbackRow[]): Record<string, unknown> {
  return buildRuleProposals(rows);
}

async function handleFeedbackEndpoint(pathname: string, req: Request): Promise<Response | null> {
  if (!pathname.includes("/feedback/")) return null;
  const rows = (await loadFeedbackRows()).map(enriched);
  const good = rows.filter((row) => row.feedback_type === "good");
  const bad = rows.filter((row) => row.feedback_type === "not_good");

  if (req.method === "GET" && pathname.endsWith("/feedback/summary")) {
    return json({
      total_feedback_count: rows.length,
      good_count: good.length,
      not_good_count: bad.length,
      negative_feedback_category_counts: countValues(bad.map((row) => row.feedback_category ?? "not_relevant_domain")),
      positive_signal_category_counts: countValues(good.map((row) => row.positive_signal_category ?? "other")),
      most_common_keywords_from_good_titles: mostCommon(good.flatMap((row) => row.extracted_title_keywords ?? [])),
      most_common_keywords_from_rejected_titles: mostCommon(bad.flatMap((row) => row.extracted_title_keywords ?? [])),
      most_common_positive_domain_terms: mostCommon(good.flatMap((row) => row.extracted_domain_terms ?? [])),
      most_common_rejected_location_terms: mostCommon(bad.flatMap((row) => row.extracted_location_terms ?? [])),
      most_recent_feedback_records: rows.slice(0, 20),
    });
  }

  if (req.method === "GET" && pathname.endsWith("/feedback/preference-profile")) {
    return json(preferenceProfile(rows));
  }

  if (req.method === "GET" && pathname.endsWith("/feedback/rule-proposals")) {
    return json(ruleProposals(rows));
  }

  if (req.method === "POST" && pathname.endsWith("/feedback/apply-rule-proposal")) {
    const body = await req.json();
    if (body.approved !== true) {
      return json({ ok: false, error: "Send approved=true to apply rule proposals." }, 403);
    }
    const proposal = body.proposal ?? ruleProposals(rows);
    const config = proposalToConfig(proposal);
    const { error } = await supabase
      .from("feedback_filter_config")
      .upsert({ key: "active", config, updated_at: new Date().toISOString() });
    if (error) return json({ ok: false, error: error.message }, 500);
    return json({ ok: true, config });
  }

  return null;
}

function proposalToConfig(proposal: Record<string, unknown>): Record<string, unknown> {
  const negative = proposal.negative_filters as Record<string, unknown> ?? {};
  const positive = proposal.positive_boosts as Record<string, unknown> ?? {};
  return {
    allowed_locations: ["US", "Remote US", "New York", "San Francisco"],
    blocked_locations: negative.blocked_locations ?? [],
    blocked_seniority_keywords: negative.blocked_seniority_keywords ?? [],
    max_years_experience: negative.max_years_experience ?? 6,
    require_hiring_signal: true,
    positive_title_boost_keywords: positive.preferred_title_keywords ?? [],
    positive_domain_boost_keywords: positive.preferred_domain_terms ?? [],
    positive_workflow_boost_keywords: positive.preferred_workflow_terms ?? [],
    positive_agent_boost_keywords: positive.preferred_agent_terms ?? [],
    positive_location_boost_terms: positive.preferred_location_terms ?? [],
    acceptable_seniority_keywords: positive.acceptable_seniority_keywords ?? [],
  };
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  if (!SUPABASE_URL || !SUPABASE_SERVICE_ROLE_KEY) {
    return json({ ok: false, error: "Feedback is not configured" }, 500);
  }

  const url = new URL(req.url);
  const feedbackEndpoint = await handleFeedbackEndpoint(url.pathname, req);
  if (feedbackEndpoint) return feedbackEndpoint;

  if (req.method === "GET") {
    const action = url.searchParams.get("action");
    const post_id = url.searchParams.get("post_id") ?? "";
    const post_url = url.searchParams.get("post_url") ?? "";
    const title = url.searchParams.get("title") ?? "LinkedIn role";

    if (!post_id) {
      return text("Missing post ID", 400);
    }

    if (action === "good") {
      return goodConfirmationPage(url);
    }

    if (action === "add_feedback") {
      if (FEEDBACK_FORM_URL) {
        return Response.redirect(feedbackFormUrl(url), 303);
      }
      return text("Feedback form URL is not configured", 500);
    }
  }

  if (req.method === "POST") {
    const contentType = req.headers.get("content-type") ?? "";
    const wantsHtml = !contentType.includes("application/json");
    let post_id = "";
    let post_url = "";
    let title = "LinkedIn role";
    let note = "";
    let feedback_type: FeedbackType = "not_good";

    if (contentType.includes("application/json")) {
      const body = await req.json();
      post_id = String(body.post_id ?? "");
      post_url = String(body.post_url ?? "");
      title = String(body.title ?? title);
      note = String(body.note ?? "").trim();
      if (body.feedback_type === "good" || body.feedback_type === "not_good") {
        feedback_type = body.feedback_type;
      }
    } else {
      const form = await req.formData();
      post_id = String(form.get("post_id") ?? "");
      post_url = String(form.get("post_url") ?? "");
      title = String(form.get("title") ?? title);
      note = String(form.get("note") ?? "").trim();
      const requestedType = String(form.get("feedback_type") ?? "");
      if (requestedType === "good" || requestedType === "not_good") {
        feedback_type = requestedType;
      }
    }

    if (!post_id || (feedback_type === "not_good" && !note)) {
      const result: SaveFeedbackResult = {
        ok: false,
        status: "error",
        message: "Missing feedback",
        httpStatus: 400,
      };
      return feedbackResponse(result, wantsHtml);
    }

    const result = await saveFeedback({
      post_id,
      post_url,
      title,
      feedback_type,
      note,
    });
    return feedbackResponse(result, wantsHtml);
  }

  return text("Not found", 404);
});
