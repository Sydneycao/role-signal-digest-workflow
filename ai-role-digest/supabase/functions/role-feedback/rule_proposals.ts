export type LearningFeedbackRow = {
  feedback_type: "good" | "not_good";
  feedback_category: string | null;
  title: string | null;
  extracted_title_keywords: string[] | null;
  extracted_location_terms: string[] | null;
  extracted_domain_terms: string[] | null;
  extracted_seniority_terms: string[] | null;
};

export const MIN_RULE_EVIDENCE = 2;

function counts(values: string[]): Map<string, { value: string; count: number }> {
  const result = new Map<string, { value: string; count: number }>();
  for (const value of values) {
    const clean = value?.trim();
    if (!clean) continue;
    const key = clean.toLowerCase();
    const current = result.get(key);
    result.set(key, { value: current?.value ?? clean, count: (current?.count ?? 0) + 1 });
  }
  return result;
}

function supported(
  positiveValues: string[],
  negativeValues: string[],
  minimum = MIN_RULE_EVIDENCE,
): string[] {
  const positive = counts(positiveValues);
  const negative = counts(negativeValues);
  return [...positive.entries()]
    .filter(([key, item]) => item.count >= minimum && item.count > (negative.get(key)?.count ?? 0))
    .sort((a, b) => {
      const aNet = a[1].count - (negative.get(a[0])?.count ?? 0);
      const bNet = b[1].count - (negative.get(b[0])?.count ?? 0);
      return bNet - aNet || b[1].count - a[1].count || a[1].value.localeCompare(b[1].value);
    })
    .map(([, item]) => item.value);
}

function conflicts(left: string[], right: string[]): string[] {
  const rightKeys = new Set(right.map((value) => value.toLowerCase()));
  return [...new Set(left.filter((value) => rightKeys.has(value.toLowerCase())).map((value) => value.toLowerCase()))]
    .sort();
}

function configTerm(term: string): string {
  if (term.toLowerCase() === "vp") return "VP";
  if (term.toLowerCase() === "head of") return "Head of";
  if (term.toLowerCase().includes("years")) return term;
  return term.replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function buildRuleProposals(rows: LearningFeedbackRow[]): Record<string, unknown> {
  const good = rows.filter((row) => row.feedback_type === "good");
  const bad = rows.filter((row) => row.feedback_type === "not_good");
  const wrongLocation = bad.filter((row) => row.feedback_category === "wrong_location");
  const tooSenior = bad.filter((row) => row.feedback_category === "too_senior");
  const notHiring = bad.filter((row) => row.feedback_category === "not_hiring_post");
  const expired = bad.filter((row) => row.feedback_category === "expired_post");

  const goodTitles = good.flatMap((row) => row.extracted_title_keywords ?? []);
  const badTitles = bad.flatMap((row) => row.extracted_title_keywords ?? []);
  const goodDomains = good.flatMap((row) => row.extracted_domain_terms ?? []);
  const badDomains = bad.flatMap((row) => row.extracted_domain_terms ?? []);
  const goodLocations = good.flatMap((row) => row.extracted_location_terms ?? []);
  const rejectedLocations = wrongLocation.flatMap((row) => row.extracted_location_terms ?? []);
  const goodSeniority = good.flatMap((row) => row.extracted_seniority_terms ?? []);
  const rejectedSeniority = tooSenior.flatMap((row) => row.extracted_seniority_terms ?? []);

  const preferredTitles = supported(goodTitles, badTitles);
  const preferredDomains = supported(goodDomains, badDomains);
  const preferredWorkflows = supported(
    goodDomains.filter((value) => /workflow|automation/i.test(value)),
    badDomains.filter((value) => /workflow|automation/i.test(value)),
  );
  const preferredAgents = supported(
    goodDomains.filter((value) => /agent|agentic|llm|rag/i.test(value)),
    badDomains.filter((value) => /agent|agentic|llm|rag/i.test(value)),
  );
  const blockedLocations = supported(rejectedLocations, goodLocations);
  const blockedSeniority = supported(rejectedSeniority, goodSeniority).map(configTerm);
  const preferredLocations = supported(goodLocations, rejectedLocations);
  const acceptableSeniority = supported(goodSeniority, rejectedSeniority);

  return {
    evidence_policy: {
      minimum_consistent_feedback: MIN_RULE_EVIDENCE,
      category_specific_negative_rules: true,
      conflict_resolution: "keep only terms with stronger same-direction evidence",
    },
    conflicts_removed: {
      title_terms: conflicts(goodTitles, badTitles),
      location_terms: conflicts(goodLocations, rejectedLocations),
      seniority_terms: conflicts(goodSeniority, rejectedSeniority),
    },
    negative_filters: {
      blocked_locations: blockedLocations,
      blocked_seniority_keywords: blockedSeniority,
      max_years_experience: tooSenior.length >= MIN_RULE_EVIDENCE ? 6 : null,
    },
    positive_boosts: {
      preferred_title_keywords: preferredTitles,
      preferred_role_archetypes: preferredTitles.filter((value) => value.includes(" ")),
      preferred_domain_terms: preferredDomains,
      preferred_workflow_terms: preferredWorkflows,
      preferred_agent_terms: preferredAgents,
      preferred_location_terms: preferredLocations,
      acceptable_seniority_keywords: acceptableSeniority,
    },
    location_rules_to_strengthen: blockedLocations,
    seniority_rules_to_refine: blockedSeniority,
    hiring_post_classifier_improvements: {
      not_hiring_post_examples: notHiring.slice(0, 10).map((row) => row.title),
      expired_post_examples: expired.slice(0, 10).map((row) => row.title),
    },
  };
}
