import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import {
  generateJobDescription,
  JobDescriptionApiError,
} from "./api/jobDescriptions";
import type {
  FieldErrors,
  JobDescriptionGenerationRequest,
  JobDescriptionGenerationResponse,
  WorkArrangement,
} from "./types/jobDescription";

interface FormValues {
  job_title: string;
  role_summary: string;
  responsibilities: string;
  required_skills: string;
  work_arrangement: WorkArrangement | "";
  location: string;
}

const RETRIEVAL_LABELS = {
  semantic_bge_pgvector: "Semantic BGE + exact pgvector cosine",
} as const;

const EMPTY_FORM: FormValues = {
  job_title: "",
  role_summary: "",
  responsibilities: "",
  required_skills: "",
  work_arrangement: "",
  location: "",
};

const DEMO_FORM: FormValues = {
  ...EMPTY_FORM,
  job_title: "Backend AI Engineer",
  role_summary:
    "Build and maintain secure AI-enabled backend services for recruitment workflows.",
  responsibilities: [
    "Develop FastAPI backend services",
    "Integrate LLM and retrieval workflows",
    "Write automated tests",
    "Follow secure software engineering practices",
  ].join("\n"),
  required_skills: ["Python", "FastAPI", "PostgreSQL", "REST API", "Git"].join("\n"),
};

function linesToItems(text: string): string[] {
  return text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
}

function FieldError({ id, message }: { id: string; message?: string }) {
  return message ? <p className="field-error" id={id}>{message}</p> : null;
}

function ResultList({ title, items }: { title: string; items: string[] }) {
  return (
    <section className="result-section" aria-label={title}>
      <h3>{title}</h3>
      <ul>{items.map((item, index) => <li key={index}>{item}</li>)}</ul>
    </section>
  );
}

function PolicyGrounding({ result }: { result: JobDescriptionGenerationResponse }) {
  const sources = new Map<string, Set<string>>();
  for (const citation of result.grounding_citations) {
    const sections = sources.get(citation.source_title) ?? new Set<string>();
    for (const path of citation.heading_paths) {
      const section = path[path.length - 1];
      if (section && section !== citation.source_title) sections.add(section);
    }
    sources.set(citation.source_title, sections);
  }

  return (
    <section className="grounding-section" aria-labelledby="grounding-title">
      <div className="grounding-header">
        <h3 id="grounding-title">Policy Grounding</h3>
        <span className="demo-badge">Demo policy source</span>
      </div>
      <p className="grounding-description">Grounded in synthetic company policy for this demo.</p>
      <ul className="policy-sources">
        {Array.from(sources, ([title, sections]) => (
          <li key={title}>
            <h4>{title}</h4>
            {sections.size > 0 && (
              <ul className="policy-sections" aria-label="Referenced policy sections">
                {Array.from(sections, (section) => <li key={section}>{section}</li>)}
              </ul>
            )}
          </li>
        ))}
      </ul>
      <details className="technical-details">
        <summary>Technical details</summary>
        <dl className="generation-metadata">
          <div><dt>Provider</dt><dd>Groq</dd></div>
          <div><dt>Model</dt><dd>{result.model}</dd></div>
          <div><dt>Retrieval</dt><dd>{RETRIEVAL_LABELS[result.retrieval_mode]}</dd></div>
        </dl>
        <h4>Citation IDs</h4>
        <ul className="technical-citations">
          {result.grounding_citations.map((citation) => (
            <li key={citation.citation_id}>
              <span>{citation.source_title}</span>
              <code>{citation.citation_id}</code>
            </li>
          ))}
        </ul>
      </details>
    </section>
  );
}

function App() {
  const [form, setForm] = useState<FormValues>(EMPTY_FORM);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [error, setError] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [result, setResult] = useState<JobDescriptionGenerationResponse | null>(null);
  const submissionInProgress = useRef(false);
  const resultHeading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    if (result) resultHeading.current?.focus({ preventScroll: true });
  }, [result]);

  function updateField<K extends keyof FormValues>(field: K, value: FormValues[K]) {
    setForm((previous) => ({ ...previous, [field]: value }));
    setFieldErrors((previous) => ({ ...previous, [field]: undefined }));
    setError("");
    setResult(null);
  }

  function loadDemo() {
    if (submissionInProgress.current) return;
    setForm({ ...DEMO_FORM });
    setFieldErrors({});
    setError("");
    setResult(null);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submissionInProgress.current) return;

    const request: JobDescriptionGenerationRequest = {
      job_title: form.job_title.trim(),
      role_summary: form.role_summary.trim(),
      responsibilities: linesToItems(form.responsibilities),
      required_skills: linesToItems(form.required_skills),
      ...(form.work_arrangement ? { work_arrangement: form.work_arrangement } : {}),
      ...(form.location.trim() ? { location: form.location.trim() } : {}),
    };
    const errors: FieldErrors = {};
    if (request.job_title.length < 2) errors.job_title = "Enter a job title of at least 2 characters.";
    if (request.role_summary.length < 20) errors.role_summary = "Describe the role in at least 20 characters.";
    if (!request.responsibilities.length) errors.responsibilities = "Add at least one responsibility.";
    if (!request.required_skills.length) errors.required_skills = "Add at least one required skill.";
    setFieldErrors(errors);
    setError("");
    setResult(null);
    if (Object.keys(errors).length) {
      setError("Please complete the required fields before generating.");
      return;
    }

    submissionInProgress.current = true;
    setIsGenerating(true);
    try {
      setResult(await generateJobDescription(request));
    } catch (failure: unknown) {
      if (failure instanceof JobDescriptionApiError) {
        setError(failure.message);
        setFieldErrors(failure.fieldErrors);
      } else {
        setError("Job description generation could not be completed. Please try again.");
      }
    } finally {
      submissionInProgress.current = false;
      setIsGenerating(false);
    }
  }

  return (
    <div className="app-shell">
      <header className="site-header">
        <a className="brand" href="/" aria-label="TalentTrace AI home">
          <span className="brand-mark" aria-hidden="true">T</span>
          <span>TalentTrace <span className="brand-ai">AI</span></span>
        </a>
        <span className="workspace-label">Recruiter workspace</span>
      </header>

      <main>
        <div className="page-intro">
          <p className="eyebrow">Evidence-backed hiring intelligence</p>
          <h1>Job Description Agent</h1>
          <p className="page-description">
            Turn role requirements into a clear, policy-grounded job description.
            Review every draft before using it.
          </p>
        </div>

        <div className="workspace-grid">
          <section className="card form-card" aria-labelledby="requirements-title">
            <div className="card-header">
              <div><h2 id="requirements-title">Role requirements</h2><p>Start with the essentials.</p></div>
              <button className="button button-secondary" type="button" onClick={loadDemo} disabled={isGenerating}>
                Load Demo Example
              </button>
            </div>

            <aside className="knowledge-source" aria-labelledby="knowledge-source-title">
              <div className="knowledge-source-heading">
                <h3 id="knowledge-source-title">Company Policy Knowledge Source</h3>
                <span className="demo-badge">Demo policy source</span>
              </div>
              <p className="knowledge-source-name">Synthetic Demo Company Policy</p>
              <dl className="knowledge-source-metadata">
                <div><dt>Status:</dt><dd>Server-side demo source</dd></div>
                <div><dt>Retrieval:</dt><dd>Semantic BGE + pgvector</dd></div>
              </dl>
              <p className="knowledge-source-explanation">
                Relevant policy sections are retrieved automatically when you generate a job description.
                Recruiters do not need to upload the company policy for each request.
              </p>
              <p className="knowledge-source-flow">Knowledge source → Retrieval → Generated grounded JD</p>
            </aside>

            <form onSubmit={handleSubmit} noValidate>
              <fieldset disabled={isGenerating}>
                <legend className="sr-only">Job description requirements</legend>
                <div className="field">
                  <label htmlFor="job-title">Job Title <span className="required-label">Required</span></label>
                  <input id="job-title" value={form.job_title} onChange={(event) => updateField("job_title", event.target.value)} placeholder="e.g. Backend AI Engineer" maxLength={120} required aria-invalid={Boolean(fieldErrors.job_title)} aria-describedby="job-title-error" />
                  <FieldError id="job-title-error" message={fieldErrors.job_title} />
                </div>

                <div className="field">
                  <label htmlFor="role-summary">Role Summary <span className="required-label">Required</span></label>
                  <p className="helper-text" id="role-summary-help">Describe the role's purpose in a sentence or two.</p>
                  <textarea id="role-summary" rows={3} value={form.role_summary} onChange={(event) => updateField("role_summary", event.target.value)} placeholder="What will this person help your team achieve?" maxLength={1000} required aria-invalid={Boolean(fieldErrors.role_summary)} aria-describedby="role-summary-help role-summary-error" />
                  <FieldError id="role-summary-error" message={fieldErrors.role_summary} />
                </div>

                <div className="field">
                  <label htmlFor="responsibilities">Responsibilities <span className="required-label">Required</span></label>
                  <p className="helper-text" id="responsibilities-help">One responsibility per line. Up to 20 items.</p>
                  <textarea id="responsibilities" rows={4} value={form.responsibilities} onChange={(event) => updateField("responsibilities", event.target.value)} placeholder={"Design and maintain backend services\nWrite automated tests"} required aria-invalid={Boolean(fieldErrors.responsibilities)} aria-describedby="responsibilities-help responsibilities-error" />
                  <FieldError id="responsibilities-error" message={fieldErrors.responsibilities} />
                </div>

                <div className="field">
                  <label htmlFor="required-skills">Required Skills <span className="required-label">Required</span></label>
                  <p className="helper-text" id="required-skills-help">One skill per line. Include only essential skills.</p>
                  <textarea id="required-skills" rows={3} value={form.required_skills} onChange={(event) => updateField("required_skills", event.target.value)} placeholder={"Python\nFastAPI\nPostgreSQL"} required aria-invalid={Boolean(fieldErrors.required_skills)} aria-describedby="required-skills-help required-skills-error" />
                  <FieldError id="required-skills-error" message={fieldErrors.required_skills} />
                </div>

                <div className="optional-fields">
                  <div className="field">
                    <label htmlFor="work-arrangement">Work Arrangement <span className="optional-label">Optional</span></label>
                    <select id="work-arrangement" value={form.work_arrangement} onChange={(event) => updateField("work_arrangement", event.target.value as WorkArrangement | "")} aria-invalid={Boolean(fieldErrors.work_arrangement)} aria-describedby="work-arrangement-error">
                      <option value="">Not specified</option><option value="on_site">On-site</option><option value="hybrid">Hybrid</option><option value="remote">Remote</option>
                    </select>
                    <FieldError id="work-arrangement-error" message={fieldErrors.work_arrangement} />
                  </div>
                  <div className="field">
                    <label htmlFor="location">Location <span className="optional-label">Optional</span></label>
                    <input id="location" value={form.location} onChange={(event) => updateField("location", event.target.value)} placeholder="e.g. Dhaka" maxLength={150} aria-invalid={Boolean(fieldErrors.location)} aria-describedby="location-error" />
                    <FieldError id="location-error" message={fieldErrors.location} />
                  </div>
                </div>
              </fieldset>

              {error && <div className="error-banner" role="alert">{error}</div>}
              <button className="button button-primary generate-button" type="submit" disabled={isGenerating}>
                {isGenerating && <span className="spinner" aria-hidden="true" />}
                {isGenerating ? "Generating job description..." : "Generate Job Description"}
              </button>
              <p className="form-note">Use role requirements only. Do not enter candidate information or confidential details.</p>
            </form>
          </section>

          <section className="card result-card" aria-labelledby="draft-title" aria-busy={isGenerating}>
            <div className="card-header"><div><h2 id="draft-title">Generated job description</h2><p>A draft for your review.</p></div></div>
            <p className="sr-only" role="status">{isGenerating ? "Generating job description..." : result ? "Draft ready. Human review required." : ""}</p>
            {result ? (
              <div className="result-content">
                <div className="draft-notice"><span className="draft-badge">Draft</span><strong>Human review required</strong><p>This draft has not been approved, saved, or published.</p></div>
                <article className="job-description">
                  <h2 className="generated-title" ref={resultHeading} tabIndex={-1}>{result.job_description.title}</h2>
                  <section className="result-section"><h3>Summary</h3><p>{result.job_description.summary}</p></section>
                  <ResultList title="Responsibilities" items={result.job_description.responsibilities} />
                  <section className="result-section"><h3>Required Skills</h3><ul className="skill-list">{result.job_description.required_skills.map((skill, index) => <li key={index}>{skill}</li>)}</ul></section>
                  {result.job_description.preferred_skills.length > 0 && <ResultList title="Preferred Skills" items={result.job_description.preferred_skills} />}
                  <ResultList title="Qualifications" items={result.job_description.qualifications} />
                </article>

                <PolicyGrounding result={result} />
              </div>
            ) : (
              <div className="empty-result">
                <div className="document-preview" aria-hidden="true"><span /><span /><span /><span /></div>
                <h3>{isGenerating ? "Your draft is on its way" : "Your draft starts here"}</h3>
                <p>{isGenerating ? "Creating a job description from your requirements and synthetic company policy." : "Add role requirements or load the demo example, then generate a job description."}</p>
                <div className="empty-result-note">Structured draft <span aria-hidden="true">·</span> Policy citations <span aria-hidden="true">·</span> Human review</div>
              </div>
            )}
          </section>
        </div>

      </main>
    </div>
  );
}

export default App;
