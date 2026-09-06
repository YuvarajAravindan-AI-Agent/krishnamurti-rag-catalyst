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
   freedom), and 15 off-corpus questions split by *why* they are
   unanswerable: unrelated topics, questions naming a teacher with zero
   occurrences in the corpus, and questions naming someone the corpus does
   contain but never as their own teaching.
3. Measures retrieval recall, citation accuracy (does every in-corpus
   answer carry a real kfoundation.org URL), an LLM-judged
   unsupported-claims rate, no-match precision on the off-corpus set, and
   latency.
4. Writes a report against fixed acceptance thresholds.
5. **Stops.** A human has to look at the report and click promote. The
   agent never touches production on its own.

## Retrieval didn't end up on QuickML, and that's the interesting part

The plan was to put retrieval on QuickML's Knowledge Base. It can't go
there. The Knowledge Base has no ingestion API — documents go in through the
console UI, ten files at a time. For a one-off migration that's tedious. For
this project it's disqualifying: an agent that cannot re-index cannot run
"re-index, then evaluate", which is the entire loop.

So retrieval moved into the AppSail container: the same `all-MiniLM-L6-v2`
model Ollama was serving, this time through ONNX Runtime, scoring an exact
dot product against a normalised matrix. 164k chunks, ~250 MB resident,
single-digit-millisecond queries, and — because it's the same model in the
same cosine space — the `MIN_RELEVANCE = 0.5` threshold carries over intact.
I measured that rather than assuming it: mean cosine agreement of 0.999998
against 300 vectors pulled out of the live Chroma collection.

QuickML kept the job it's genuinely good at: synthesis, off-box, away from
AppSail's 30-second ceiling.

## Two things the evaluation caught

**A live bug in the app I was migrating away from.** Ask the production
Netcup site "what did Osho teach about meditation?" and it scores 0.618,
sails past its own threshold, and answers. The question is legitimately
about meditation, so cosine distance cannot reject it. Every named-teacher
question in the set did this. The fix is a second gate that refuses
questions naming proper nouns absent from the corpus — with every name it
knows derived from the corpus itself, because a hardcoded list of rival
teachers would just be tuned to my own traps.

**An error in my evaluation set.** I had labelled seven questions as traps
whose subjects were "genuinely absent". Four weren't. K discusses the
Bhagavad Gita 803 times, refers to Rajneesh, describes meeting the Dalai
Lama. On Ramana Maharshi, Gstaad, 16 August 1962: *"I don't know these
birds… Why should I know them?"*

They're still unanswerable — the archive contains his refusal of the
subject, not the teaching — but that's a different and harder failure than
"the name isn't there", and no proper-noun gate can catch it. So the
honest scoreboard is 3/3 on absent-person questions, 8/8 on unrelated ones,
25/25 in-corpus, and 0/4 on the category I only discovered by being wrong.

That last number stays in the report. A demo tuned until everything passes
demonstrates nothing; the reason to build a judge is that it can tell you
your own scoring was wrong.

## What's next

- [ ] QuickML LLM Serving wired for synthesis
- [ ] Index served from Stratus object storage at container start
- [ ] 30-day parallel run against the Netcup original before decommissioning it
- [ ] A recorded walkthrough of the agent's reject run — that's the actual
      demo, not the RAG app itself
- [ ] A real answer for `mentioned-not-taught`, which is currently an open
      problem rather than a solved one

GitHub: [link] · Live app: [link] · LinkedIn: [link]
