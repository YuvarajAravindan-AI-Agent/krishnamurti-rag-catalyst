# Podcast source: Krishnamurti RAG on Zoho Catalyst 3.0

## Suggested title

From Netcup to Agentic DevOps: A Release-Quality Agent for a RAG App

## Episode brief

This 6–8 minute technical podcast explains a RAG migration used as a
substrate for demonstrating Catalyst 3.0's agentic DevOps pitch. A
self-hosted FastAPI + Ollama + Chroma app answering questions over ~3,000
J. Krishnamurti public talks moves to Zoho Catalyst's QuickML (managed
retrieval + LLM serving) and AppSail (hosting). The actual subject of the
podcast is the release-quality agent built on top of it: on any
corpus/prompt/model change, it re-indexes, runs a 40-question golden
evaluation suite (including adversarial off-corpus traps naming real but
absent teachers — Osho, Ramana Maharshi, Eckhart Tolle), measures retrieval
recall/citation accuracy/unsupported-claims rate/no-match precision/latency,
and produces an accept/reject recommendation — then stops for human
approval before promoting to production.

## Important accuracy notes

- The migration replaces Ollama/Chroma with QuickML entirely — it is not a
  lift-and-shift. AppSail's 30-second request limit made the original
  Ollama-based synthesis (measured up to 47s to first token) a genuine
  timeout risk, not lifted over.
- Full-corpus ingestion (3,014 transcripts) is a follow-up batch job — the
  demo runs against a representative subset because QuickML's Knowledge
  Base has no bulk-upload API, only a manual console UI capped at 10
  files/round.
- The agent never promotes to production itself; a human always approves.
- The deliberate-regression run (staged after the first clean promotion) is
  a real recorded run, not a hypothetical — state its actual outcome once
  available rather than assuming pass/fail.
- The model must never be treated as ground truth for whether a K quote is
  authentic — citations point back to the original kfoundation.org URL for
  verification.

## Technical outline

1. Why migrate: cost/ops burden of a self-managed VPS vs. wanting to
   demonstrate Catalyst 3.0's agentic DevOps tooling specifically.
2. Architecture change: AppSail (FastAPI + static UI) → QuickML RAG/
   Knowledge Base (retrieval) → QuickML managed LLM (synthesis).
3. The golden evaluation set: why adversarial "adjacent-but-wrong" traps
   (named philosophers who sound on-topic but aren't K) stress no-match
   precision harder than random off-corpus questions would.
4. The release-quality agent's loop: re-index → deploy to Development →
   evaluate → inspect logs → report → stop for human approval.
5. The regression demo: what changed, what the agent measured, what it
   recommended, and why that's the actual point of the whole exercise.
6. Observability: Catalyst Logs/Alerts/Metrics as the evidence source for
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
