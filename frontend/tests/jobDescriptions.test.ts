import assert from "node:assert/strict";
import { test } from "node:test";
import { generateJobDescription, JobDescriptionApiError } from "../src/api/jobDescriptions.ts";

const request = {
  job_title: "Backend Engineer",
  role_summary: "Build reliable backend services.",
  responsibilities: ["Write automated tests"],
  required_skills: ["Python"],
};

function responseBody(mode = "semantic_bge_pgvector") {
  return {
    status: "draft",
    human_review_required: true,
    provider: "groq",
    model: "openai/gpt-oss-120b",
    retrieval_mode: mode,
    job_description: {
      title: request.job_title,
      summary: request.role_summary,
      responsibilities: request.responsibilities,
      required_skills: request.required_skills,
      preferred_skills: [],
      qualifications: ["Equivalent professional experience"],
      policy_citation_ids: ["synthetic-test-citation"],
    },
    grounding_citations: [{
      citation_id: "synthetic-test-citation",
      source_title: "Synthetic Demo Company Policy",
      heading_paths: [["Skills and Qualifications"]],
    }],
  };
}

test("runtime validation accepts the semantic mode with draft/review guarantees", async (t) => {
  t.mock.method(globalThis, "fetch", async () => Response.json(responseBody()));
  const result = await generateJobDescription(request);
  assert.equal(result.retrieval_mode, "semantic_bge_pgvector");
  assert.equal(result.status, "draft");
  assert.equal(result.human_review_required, true);
});

for (const mode of ["deterministic_lexical_demo", "unknown_retrieval"]) {
  test(`runtime validation rejects ${mode} instead of showing semantic labels`, async (t) => {
    t.mock.method(globalThis, "fetch", async () => Response.json(responseBody(mode)));
    await assert.rejects(generateJobDescription(request), JobDescriptionApiError);
  });
}

test("runtime validation rejects an unreviewed guarantee change", async (t) => {
  const body = { ...responseBody(), human_review_required: false };
  t.mock.method(globalThis, "fetch", async () => Response.json(body));
  await assert.rejects(generateJobDescription(request), JobDescriptionApiError);
});
