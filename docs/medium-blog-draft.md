# Jiddu Krishnamurti RAG: Netcup to Catalyst 3.0 — and the agent that guards the release

## The setup

For a while I've run a small RAG app that answers questions over roughly
3,000 public talk transcripts by J. Krishnamurti, sourced from
kfoundation.org. It lived on a self-managed Netcup VPS: FastAPI, Ollama for
local embeddings and chat, Chroma for the vector store, Caddy for TLS. It
worked, but it was mine to patch, restart, and pay for every month.

Zoho's Catalyst 3.0 launch made a specific claim worth testing: **agentic
DevOps** — Agent Skills, MCP, a non-interactive CLI, Pipelines, Job
Scheduling, all aimed at letting an agent run real operational work, not
just answer chat questions. I wanted to see if that claim held up on a real
workload, not a toy one.

## Why not just lift-and-shift?

The obvious move — put Ollama and Chroma inside an AppSail container — is
also the wrong one. AppSail's request limit is 30 seconds; my own measured
worst case for first-token latency on a hard CPU query was 47 seconds. That
isn't a timeout risk, it's a timeout certainty. So the migration is a real
architecture change: QuickML's managed retrieval and LLM serving replace
Ollama and Chroma outright, not a rehost with extra steps.

## What actually matters here

A RAG app answering questions on Catalyst doesn't demonstrate anything
Catalyst-specific — any hosting platform can serve an HTTP endpoint. What's
worth demonstrating is the release discipline Catalyst's agentic tooling
makes possible: an agent that treats "did this corpus/prompt/model change
make the app worse" as a question with a measurable answer, not a vibe.

So I built a release-quality agent. On any change to the corpus, the
retrieval config, or the prompt, it:

1. Re-indexes the affected documents into QuickML's Knowledge Base
2. Runs a 40-question golden evaluation suite against the candidate —
   25 in-corpus questions spanning K's recurring themes (fear, authority,
   self-knowledge, relationship, awareness, thought, love, truth, memory,
   freedom), and 15 off-corpus questions, including adversarial
   "adjacent-but-wrong" traps: questions about Osho, Ramana Maharshi,
   Eckhart Tolle — real teachers whose material is genuinely absent from
   this corpus, chosen specifically because a lazy retrieval system would
   be tempted to answer them anyway.
3. Measures retrieval recall, citation accuracy (does every in-corpus
   answer carry a real kfoundation.org URL), an LLM-judged
   unsupported-claims rate, no-match precision on the off-corpus set, and
   latency.
4. Writes a report against fixed acceptance thresholds.
5. **Stops.** A human has to look at the report and click promote. The
   agent never touches production on its own.

## The part worth actually watching

Anyone can demo the happy path. What proves the safety boundary is real is
watching it catch a regression. So after the first clean promotion, I made
a deliberate change — shrinking chunk overlap enough to plausibly hurt
citation accuracy — and ran the agent again. [Result to be filled in once
the shadow test / regression run completes: recommendation, which metric
failed, by how much.]

## What's next

- [ ] Full 3,014-transcript ingestion (a manual/batched follow-up — QuickML's
      Knowledge Base has no bulk upload API, only a console UI capped at
      10 files/round)
- [ ] 30-day parallel run against the Netcup original before decommissioning it
- [ ] A recorded walkthrough of the agent's reject run — that's the actual
      demo, not the RAG app itself

GitHub: [link] · Live app: [link] · LinkedIn: [link]
