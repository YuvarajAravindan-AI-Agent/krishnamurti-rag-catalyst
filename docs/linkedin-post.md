# LinkedIn post — final

**Title:** Jiddu Krishnamurti RAG — Netcup to Catalyst 3.0 migration project

Attach: `krishnamurti-rag-catalyst-demo.mp4` (50s)
First comment: GitHub repo link.

---

I migrated a RAG app answering questions over ~3,000 J. Krishnamurti public
talk transcripts off a self-managed Netcup VPS (FastAPI + Ollama + Chroma)
onto Zoho Catalyst 3.0.

The migration isn't the interesting part. Catalyst 3.0's pitch is agentic
DevOps, and a RAG app answering questions showcases none of that. So the
actual deliverable is an agent that owns the release cycle:

→ Re-indexes on any corpus, prompt, or model change
→ Runs a 40-question golden evaluation suite
→ Measures recall, citation accuracy, no-match precision, latency
→ Writes an evidence-backed accept/reject recommendation
→ Stops. A human clicks promote.

Two things it caught that I wasn't looking for.

First, a live defect in the app I was migrating away from. Ask the running
production site "what did Osho teach about meditation?" and it scores 0.618
against its own relevance threshold and answers confidently. The question is
genuinely about meditation, so cosine distance has no way to reject it. It
had been doing that for months.

Second — and this is the one I keep thinking about — it caught an error in
my own evaluation set. I'd labelled seven named-teacher questions as traps
whose subjects were "absent from the corpus". Four weren't. Krishnamurti
discusses the Bhagavad Gita 803 times, refers to Rajneesh, describes meeting
the Dalai Lama. On Ramana Maharshi, in Gstaad in 1962: "I don't know these
birds… Why should I know them?"

Those questions are still unanswerable — the archive holds his refusal of
the subject, not the teaching — but that is a different and harder problem
than the one I thought I was solving.

Then it got worse, in the useful way. I made the scorer record *which*
mechanism refused each question, not just that one was refused. One of my
remaining "passes" turned out to be luck: the Dalai Lama question is refused
only because "Dalai" happens to occur twice in the corpus, under the entity
gate's threshold. One more mention anywhere in 3,000 transcripts and it
silently starts answering. Nothing about the system would have changed —
only the luck would have run out.

Scored honestly: 25/25 in-corpus, 8/8 unrelated, 3/3 genuinely-absent, and
0/4 on the category I only found by being wrong. No-match precision 0.733
against a 0.90 threshold.

So the agent's verdict on my own build is REJECT. I could clear it by moving
the threshold to 0.75. That is exactly the move worth not making.

A demo tuned until everything passes proves nothing. One that can tell you
your own scoring was wrong is worth building.

#ZohoCatalyst #AgenticDevOps #RAG #AIEngineering #LLM
