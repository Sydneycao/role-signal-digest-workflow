import { assertEquals } from "jsr:@std/assert@1";
import { buildRuleProposals, LearningFeedbackRow } from "./rule_proposals.ts";

function row(
  feedback_type: "good" | "not_good",
  category: string | null,
  seniority: string[] = [],
  locations: string[] = [],
  titles: string[] = [],
): LearningFeedbackRow {
  return {
    feedback_type,
    feedback_category: category,
    title: "Example",
    extracted_title_keywords: titles,
    extracted_location_terms: locations,
    extracted_domain_terms: [],
    extracted_seniority_terms: seniority,
  };
}

Deno.test("negative rules require two category-specific examples", () => {
  const proposal = buildRuleProposals([
    row("not_good", "wrong_location", [], ["Canada"]),
    row("not_good", "too_senior", ["principal"]),
    row("not_good", "too_senior", ["principal"]),
    row("not_good", "not_hiring_post", ["senior"], ["UK"]),
  ]);
  const negative = proposal.negative_filters as Record<string, unknown>;
  assertEquals(negative.blocked_locations, []);
  assertEquals(negative.blocked_seniority_keywords, ["Principal"]);
});

Deno.test("conflicting terms are resolved by stronger evidence", () => {
  const proposal = buildRuleProposals([
    row("good", null, ["intern"], [], ["AI Builder"]),
    row("not_good", "too_senior", ["intern"], [], ["AI Builder"]),
    row("not_good", "too_senior", ["intern"], [], ["AI Builder"]),
  ]);
  const negative = proposal.negative_filters as Record<string, unknown>;
  const positive = proposal.positive_boosts as Record<string, unknown>;
  assertEquals(negative.blocked_seniority_keywords, ["Intern"]);
  assertEquals(positive.acceptable_seniority_keywords, []);
  assertEquals(positive.preferred_title_keywords, []);
});

Deno.test("one positive example does not create a boost", () => {
  const proposal = buildRuleProposals([
    row("good", null, [], [], ["AI Builder"]),
  ]);
  const positive = proposal.positive_boosts as Record<string, unknown>;
  assertEquals(positive.preferred_title_keywords, []);
});
