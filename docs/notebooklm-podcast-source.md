# Podcast source: Krishnamurti RAG on Zoho Catalyst 3.0

## Suggested title

From Netcup to Agentic DevOps: A Release-Quality Agent for a RAG App

## Episode brief

This 6–8 minute technical podcast explains a RAG migration used as a
substrate for demonstrating Catalyst 3.0's agentic DevOps pitch. A
self-hosted FastAPI + Ollama + Chroma app answering questions over ~3,000
J. Krishnamurti public talks moves to Zoho Catalyst's QuickML (managed
LLM serving) and AppSail (hosting). The actual subject of the podcast is the
release-quality agent built on top of it: on any corpus/prompt/model change,
it re-indexes, runs a 40-question golden evaluation suite, measures retrieval
recall/citation accuracy/unsupported-claims rate/no-match precision/latency,
and produces an accept/reject recommendation — then stops for human approval
before promoting to production.

The strongest material is that the evaluation caught two things nobody was
looking for: a live defect in the app being migrated away from, and an error
in the evaluation set itself.

## Important accuracy notes

- Retrieval did NOT move to QuickML. Its Knowledge Base has no ingestion API
  — console UI only, ten files per round — so an agent cannot re-index, which
  disqualified it. Retrieval runs inside the AppSail container using the same
  all-MiniLM-L6-v2 model the original served via Ollama. QuickML is used for
  synthesis only. Do not describe this as "moving to QuickML RAG".
- AppSail's 30-second request limit made the original Ollama-based synthesis
  (measured up to 47s to first token) a genuine timeout risk. That is why
  synthesis left the box, and it is a real architecture change, not a rehost.
- The full 163,829-chunk archive IS indexed. Its vectors were exported from
  the original Chroma collection rather than recomputed, because they were
  first measured as equivalent (mean cosine agreement 0.999998).
- MIN_RELEVANCE = 0.5 carried over unchanged, and that was verified by
  measurement, not assumed. Say so this way round; the claim only holds
  because the embedding model is identical.
- The Osho example is real and was observed on the live production site:
  it scores 0.618 and answers. Do not soften this into a hypothetical.
- CRITICAL — do not repeat the claim that Rajneesh, Ramana Maharshi, the
  Bhagavad Gita or the Dalai Lama are "absent from the corpus". An earlier
  draft said that and it is false. K discusses the Gita 803 times, refers to
  Rajneesh, and describes meeting the Dalai Lama. On Ramana Maharshi
  (Gstaad, 16 August 1962) he says "I don't know these birds... Why should I
  know them?" Those questions remain unanswerable because the corpus holds
  his refusal of the subject rather than the teaching — a distinct and
  currently unsolved failure mode, scored 0/4 and reported as open.
- Only three questions (Osho, Nietzsche, Eckhart Tolle) name people with zero
  corpus occurrences. The entity gate handles those 3/3, with zero false
  positives on the 25 in-corpus questions.
- The agent never promotes to production itself; a human always approves.
- The deliberate-regression run is a real recorded run, not a hypothetical —
  state its actual outcome once available rather than assuming pass/fail.
- The model must never be treated as ground truth for whether a K quote is
  authentic — citations point back to the original kfoundation.org URL for
  verification.

## Technical outline

1. Why migrate: cost/ops burden of a self-managed VPS vs. wanting to
   demonstrate Catalyst 3.0's agentic DevOps tooling specifically.
2. Why the obvious architecture was rejected twice — Ollama couldn't stay
   (30s AppSail limit vs 47s measured synthesis), and QuickML's Knowledge
   Base couldn't take retrieval (no ingestion API, so no agent-driven
   re-index). What's left: retrieval in-process, synthesis on QuickML.
3. The golden evaluation set, and why the interesting axis is *why* a
   question is unanswerable rather than just whether it is.
4. The two findings: a live no-match defect in the production app, and the
   mislabelled eval categories the corpus itself disproved.
5. The release-quality agent's loop: re-index → deploy to Development →
   evaluate → inspect logs → report → stop for human approval.
6. The regression demo: what changed, what the agent measured, what it
   recommended, and why that's the actual point of the whole exercise.
7. Observability: Catalyst Logs/Alerts/Metrics as the evidence source for
   the agent's own report.

## Source links

- GitHub: [to be filled in once repo is public]
- Hosted app: [to be filled in once AppSail deployment is live]
- Migration plan: docs/migration-plan.md in the repo
- Netcup original (rollback target): https://jk.ai-agentic-enterprises.com
- Catalyst 3.0: https://catalyst.zoho.com/blog/meet-catalyst-3.0.html

## NotebookLM generation prompt

Create a technically credible two-host podcast for software engineers and
platform architects. Explain why a RAG migration is being used to
demonstrate agentic DevOps rather than being the point itself, the
retrieval architecture change (why lift-and-shift was rejected), the design
of an adversarial golden evaluation set, and the release-quality agent's
evaluate-then-stop-for-approval loop. Use the source links only for claims.
Do not claim the full 3,014-transcript corpus is ingested unless the source
material confirms it, and do not state the regression demo's outcome unless
it's given in the source material. End with an invitation to inspect the
GitHub repository and try the live app.
