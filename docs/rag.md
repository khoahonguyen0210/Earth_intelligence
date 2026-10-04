# Retrieval over the Docs

Ask Earth can answer questions about the system itself, such as how
accurate the model is, where its data comes from, or whether the API has
a login, by retrieving passages from `docs/` and citing them. The
planner calls this through one more approved tool, `search_docs`, so
the flow is unchanged: one plan, validated, then executed.

## Pipeline

```text
docs/*.md -> chunks -> Gemini embeddings -> index (ml/artifacts/docs_index_v1)
question  -> planner picks search_docs -> query embedding -> top 5 passages
          -> answer cites [docs/...] -> number and citation check
```

- **Chunking** (`rag/chunking.py`): each Markdown section becomes one
  chunk, and long sections are split on paragraph boundaries at about
  1,500 characters. Every chunk keeps its file path, document title and
  section heading. Sentences about the private build plan are dropped,
  so passages describe only the system. This file is left out of the
  index, because it quotes the evaluation questions and would let the
  index answer its own test set.
- **Embeddings** (`rag/embeddings.py`): `gemini-embedding-001`, 3,072
  dimensions, normalised to unit length so a dot product is cosine
  similarity. Passages are embedded as `RETRIEVAL_DOCUMENT` and
  questions as `RETRIEVAL_QUERY`. A rate-limited batch (HTTP 429) waits
  out the per-minute quota and is retried.
- **Index** (`rag/index.py`): the vectors are a NumPy matrix on disk,
  searched exactly. At 473 vectors an exact search takes milliseconds,
  so a vector database would add infrastructure without adding speed.
  The index also keeps a BM25 model of the same chunks.
- **Answering** (`planner/generate_answer.py`): retrieved passages are a
  new fact category, `documented`. The model must cite each one it uses
  by path, like `[docs/evaluation.md]`, and is told that passage text is
  data, never instructions.
- **Checking** (`planner/groundedness.py`): on top of the number check,
  every cited path must be one of the retrieved passages. Citing a doc
  that was never retrieved fails the check and is shown as a warning.

## Measured retrieval quality

`scripts/rag/evaluate_retrieval.py` runs 35 labelled questions
(`rag/eval_set.py`) through three retrieval modes. Each question lists
the docs that answer it. A retrieval is a hit when one of those docs is
in the results. The questions are deliberately worded unlike the docs,
for example "Do users need to log in?" rather than "authentication".

| Mode | Recall@1 | Recall@3 | Recall@5 | MRR |
|---|---|---|---|---|
| BM25 (keywords) | 0.371 | 0.571 | 0.714 | 0.487 |
| Dense (Gemini embeddings) | **0.857** | **0.943** | **0.971** | **0.907** |
| Hybrid (reciprocal rank fusion) | 0.629 | 0.857 | 0.914 | 0.741 |

What this shows:

- Dense retrieval is clearly best. It misses only one question in the
  top 5 ("Where are large output files kept?", which needs the object
  storage doc).
- Keyword search fails on paraphrases. It misses 10 of 35 in the top 5.
- Hybrid is worse than dense alone. Equal-weight fusion lets BM25's
  wrong matches displace correct dense results.

So the served tool uses dense retrieval. It falls back to BM25 when no
embedding client is available, or when the question cannot be embedded
immediately, for example because the embedding quota is used up. A
request never waits on the quota, and the result's `retrieval` field
says which method found the passages. The fusion weights were not
tuned to rescue hybrid, because tuning on these 35 questions would
overfit the same set used to measure it.

Limits of this measurement:

- 35 questions is small, and the same author wrote the questions and
  labelled their answers.
- Relevance is judged per document, not per passage. A hit means the
  right file was retrieved, not that the exact sentence was.
- Paraphrased questions favour embeddings by design. Questions that
  reuse the docs' own terms would narrow the gap to BM25.

## End to end

One live question, run through the real planner, retrieval and answer
generation:

> Does the forecast model actually beat a simple rule that assumes
> fires continue where they burned yesterday?

- The planner produced a single `search_docs` step.
- Four of the five passages came from `docs/evaluation.md`.
- The answer gave the +0.068 PR-AUC lead (interval +0.031 to +0.101)
  and cited `[docs/evaluation.md]`.
- The check verified all 13 numbers in the answer and found no
  unsupported citation.

## Rebuilding

```bash
python scripts/rag/build_docs_index.py     # needs GEMINI_API_KEY
python scripts/rag/evaluate_retrieval.py
```

The index must be rebuilt whenever `docs/` changes. A rebuild reuses
the stored vector of every chunk whose text is unchanged and embeds only
new or edited chunks. Each embedded chunk is one request against the
free tier's 1,000 a day, so adding a doc costs a few dozen requests,
not the roughly 480 of a build from scratch. The manifest records a
fingerprint of the chunk text, so a stale index can be spotted by
comparing fingerprints. `--lexical-only` builds a BM25-only index
without calling the API.
