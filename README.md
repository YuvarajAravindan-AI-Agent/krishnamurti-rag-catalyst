# Krishnamurti RAG — Netcup to Catalyst 3.0 migration

A retrieval-augmented Q&A app over ~3,000 J. Krishnamurti public talk
transcripts (source: [kfoundation.org](https://kfoundation.org)), migrated
from a self-hosted Netcup VPS (FastAPI + Ollama + Chroma) to
[Zoho Catalyst 3.0](https://catalyst.zoho.com/blog/meet-catalyst-3.0.html) —
built specifically to demo **agentic DevOps**, Catalyst 3.0's core pitch.

The RAG app is the substrate. The actual point is the **release-quality
agent** in [`agent/release_quality_agent.py`](agent/release_quality_agent.py):
on any corpus/prompt/model change it re-indexes, runs a golden evaluation
suite, measures retrieval quality end to end, and produces an
evidence-backed accept/reject recommendation — then **stops and waits for a
human to click promote**. No autonomous production promotion, ever.

## Architecture

```
Browser  →  AppSail (FastAPI, one origin)
                →  QuickML RAG / Knowledge Base   (retrieval)
                →  QuickML managed LLM             (synthesis)
Job Scheduling + Pipelines + Logs for the agent loop
```

Caddy + Ollama + Chroma are gone entirely — Catalyst's AppSail handles TLS,
domain mapping, and hosting; QuickML replaces the local embedding/retrieval
stack. See [`krishnamurti-rag-catalyst-migration-plan.md`](docs/migration-plan.md)
for the full execution plan this was built from.

## Layout

- `appsail/` — the FastAPI app + static query UI, deployed as a Docker Image
  AppSail service
- `agent/` — the release-quality agent (non-interactive CLI, meant to run via
  Catalyst Pipelines/Job Scheduling)
- `eval/golden_set.json` — 25 in-corpus + 15 off-corpus questions, used by both
  the retrieval-threshold calibration and the agent's evaluation pass. The
  off-corpus half is split by *why* it is unanswerable, which turns out to
  matter: `random` (unrelated topic), `absent-person` (names a teacher with
  zero occurrences in the corpus), and `mentioned-not-taught` (names someone
  the corpus does contain, but only as K's passing reference or refusal —
  never their own teaching)
- `scripts/` — one-off migration scripts (transcript splitting, demo subset
  selection)

## Status

- [x] Source data frozen and exported from the Netcup box
- [x] Golden evaluation set expanded (8+8 → 25+15) and re-labelled by failure mode
- [x] Catalyst project created (`krishnamurti-rag-catalyst`, DC: in)
- [x] Retrieval moved in-process; full 163,829-chunk archive carried over
- [x] `MIN_RELEVANCE = 0.5` verified to transfer (measured, not assumed)
- [x] Shadow test vs the Netcup app on the golden set
- [x] Corpus-derived entity gate for absent-person questions
- [ ] QuickML LLM Serving endpoint wired for synthesis
- [ ] Index delivered from Stratus object storage at container start
- [ ] AppSail deployment live
- [ ] Release-quality agent run end-to-end, including a staged regression
- [ ] Netcup box decommissioned after a 30-day rollback window

## Why not lift-and-shift Ollama + Chroma?

AppSail's request limit is 30s; the original Ollama-based synthesis measured
up to 47s to first token on hard CPU cases. QuickML's managed LLM serving
avoids that live-timeout risk entirely — this is a genuine architecture
change, not a rehost.

## Why retrieval is *not* on QuickML

The original plan put retrieval on QuickML's Knowledge Base. It can't go
there: the Knowledge Base has no ingestion API. Documents go in through the
console UI, ten files per round, which means an agent cannot re-index on a
corpus change — and "re-index, evaluate, recommend" is the entire premise of
the release-quality agent. A human clicking through 302 upload rounds is not
a step an agent can own.

So retrieval runs in-process: `all-MiniLM-L6-v2` via ONNX Runtime (the same
model Ollama served, so the cosine space is unchanged) and an exact dot
product against a normalised float32 matrix. At 164k chunks that is ~250 MB
resident and single-digit-millisecond queries, with no ANN recall error to
confound the agent's metrics. QuickML keeps the job it is actually good at:
synthesis, off-box, away from AppSail's 30s ceiling.

## What the shadow test found

Running the golden set against the live Netcup box's own Chroma collection
turned up a defect in the *original*, not the migration: every named-teacher
question clears `MIN_RELEVANCE`. Asked "what did Osho teach about
meditation?", the production app scores 0.618 and synthesises a confident
answer. The question is genuinely on-topic — it's about meditation — so
cosine distance has no way to reject it.

The fix is [`appsail/entity_gate.py`](appsail/entity_gate.py): refuse
questions naming proper nouns the corpus does not contain. Every name it
knows is derived from the corpus itself; there is no hardcoded list of rival
teachers, because such a list would be tuned to this eval set's own traps and
would prove nothing about anything else.

It also corrected the eval set. Four questions labelled as traps turned out
to name people the corpus *does* contain — K refers to Rajneesh, discusses
the Gita 803 times, and describes meeting the Dalai Lama. On Ramana Maharshi
(Gstaad, 16 August 1962) he says: *"I don't know these birds… Why should I
know them?"* Those questions are still unanswerable, but for a harder reason
— the corpus holds his *refusal of* the subject, not the teaching — and a
proper-noun gate structurally cannot catch that. It is recorded as an open
failure mode rather than papered over.

Current results on the full archive:

Measured against the live deployment. A refusal counts only when the
mechanism that fired is the one the category expects — `expected_gate` in
`eval/golden_set.json` — because a refusal by the wrong mechanism will
disappear the moment the corpus shifts.

| category | want | correctly refused | notes |
| --- | --- | --- | --- |
| in-corpus (25) | answer | 25/25 | no gate false positives |
| `random` (8) | refuse | 8/8 | all by cosine, incl. "capital of France" |
| `absent-person` (3) | refuse | 3/3 | all by the entity gate |
| `mentioned-not-taught` (4) | refuse | **0/4** | 3 answered at 0.55–0.62; 1 accidental |

That last row is the open problem. The Dalai Lama question *is* refused, but
only because `Dalai` occurs twice — under `KNOWN_ENTITY_MIN = 3`. One more
mention anywhere in the archive and it silently starts being answered, with
nothing about the handling having changed. The agent scores it as a miss.

No-match precision is therefore **0.733** against a 0.90 threshold, and the
release agent's verdict on this build is **REJECT**. Lowering the threshold
would make it pass; that is the move this project exists to argue against.

## Live app

Running on Catalyst AppSail (Development). Synthesis is not yet wired, so it
returns cited passages without a generated summary — the part that is
actually load-bearing. The URL will be published here once QuickML LLM
Serving is connected.

Netcup original (rollback target during transition): https://jk.ai-agentic-enterprises.com
