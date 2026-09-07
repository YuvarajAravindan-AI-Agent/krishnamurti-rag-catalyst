# LinkedIn post — final

**Title:** Agentic DevOps on Zoho Catalyst 3.0 — an agent that refused to ship my own build

Attach: `krishnamurti-rag-catalyst-demo.mp4` (62s)
First comment: GitHub repo link.

---

Catalyst 3.0's headline is agentic DevOps. I wanted to find out what that
actually buys you, so I gave an agent the release cycle of a real RAG app —
~3,000 J. Krishnamurti talk transcripts, migrated off a self-managed Netcup
VPS — and let it decide whether the build was fit to ship.

Here is the gap it exists to fill.

Your pipeline runs. Tests are green, the container is healthy, the deploy
succeeded. None of that tells you whether retrieval quality regressed, or
whether the app still refuses the questions it ought to refuse. A RAG app
degrades without a single failing test: change the corpus, the chunker, or
the embedding model and every assertion still passes while the answers
quietly get worse.

So the agent owns a loop, not a step:

→ re-index on any corpus, chunker, or model change
→ deploy the candidate to Development
→ run a 40-question golden evaluation suite
→ measure recall, citation accuracy, no-match precision, latency
→ write an evidence-backed accept/reject recommendation
→ stop — a human promotes to Production

Step six is the design, not a limitation. The agent assembles the evidence.
It never promotes anything itself.

One rule ended up shaping every architectural decision: **if a human has to
click it, an agent cannot own it.**

That rule cost me my original plan. Retrieval was supposed to live on
QuickML's Knowledge Base — but it has no ingestion API. Documents go in
through the console, ten files per round, which at this corpus is 302 rounds
of clicking. An agent can never re-index through that, and "re-index and
evaluate" is the entire premise. So it was cut, and retrieval moved
in-process. The same rule forced a multipart upload path to Stratus, because
the index is 126 MB and AppSail kills any request at 30 seconds.

Then the loop earned its keep, three times.

It found a live defect in the app I was migrating away from. Ask the running
production site "what did Osho teach about meditation?" and it scores 0.618
against its own relevance threshold and answers confidently. The question is
genuinely about meditation, so cosine distance has no way to reject it. It
had been doing that for months.

It found an error in my own evaluation set. I'd labelled seven named-teacher
questions as traps whose subjects were absent from the corpus. Four weren't.
Krishnamurti discusses the Bhagavad Gita 803 times, refers to Rajneesh,
describes meeting the Dalai Lama.

And it found a test that was passing by luck. I made the scorer record
*which* mechanism refused each question, not merely that one was refused.
One remaining "pass" turned out to be an accident: the Dalai Lama question is
refused only because "Dalai" happens to occur twice in the corpus, just under
the entity gate's threshold. One more mention anywhere in 3,000 transcripts
and it silently starts answering. Nothing about the system would have
changed — only the luck would have run out.

Scored honestly: 25/25 in-corpus, 8/8 unrelated, 3/3 genuinely-absent, and
0/4 on the category I only found by being wrong. No-match precision 0.733
against a 0.90 threshold.

So the agent's verdict on my own build is REJECT, and it stops there. I could
clear it by moving the threshold to 0.75 — which is exactly the move an agent
must never be allowed to make on its own behalf.

Agentic DevOps is the stop, not the speed. An agent that ships everything is
just automation. One that assembles the evidence and then refuses to ship is
the part worth building.

#ZohoCatalyst #AgenticDevOps #RAG #AIEngineering #LLM #MLOps
