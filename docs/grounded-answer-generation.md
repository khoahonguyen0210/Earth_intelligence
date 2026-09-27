# Grounded Answer Generation — LOCKED

This document freezes grounded answer generation. It is not a
brainstorming document. It builds on `docs/plan-validator.md` and
`docs/natural-language-planner.md` rather than redefining
either.

## Scope: this task consumes execution results, it does not produce them

"The final answer can summarize only execution results + evidence"
presupposes those results already exist. Actually executing a validated
`Plan` -- turning each step into a real tool call, resolving
`$step_id.field` references to real values -- is the job of a later
workflow engine, a separate set of tasks (DAG schema, state machine,
execution, persistence). Building even a minimal version of that here
would be implementing future task content, which the handbook's own
task-implementation prompt (`docs/PROMPT_SYSTEM.md` §4) rules out.

So `generate_answer` takes execution results as an input:

```python
@dataclass(frozen=True)
class StepResult:
    step_id: str
    tool: str
    result: Any
    evidence: dict[str, Any] | None = None
```

This is the minimal shape needed here, not a preview of the later
workflow engine's real result type. `tests/planner/test_generate_answer.py` never
fabricates a `StepResult`'s `result`/`evidence` by hand-typing a
plausible-looking dict -- every test builds one from genuine calls to
the real underlying functions (`query.statistics.count`,
`query.evidence.build_evidence`), so the fixtures are real values, not
guesses at what those functions might return.

## observed / computed / predicted

```python
RESULT_CATEGORY_BY_TOOL = {
    "get_data": "observed",
    "calculate_statistics": "computed",
    "generate_map": "computed",
    "run_forecast": "predicted",
    "get_forecast_result": "predicted",
    "search_docs": "documented",
}
```

Six of the eight tools appear. `documented` facts are passages from
`docs/`; the answer must cite each one it uses by path. `resolve_region` is absent: it
resolves geometry, it does not produce a fact about the world worth
stating in an answer. `get_result_evidence` is absent too: it fetches
metadata about a fact another step already produced, it is not itself a
fact. A step whose tool isn't in this table, or that has no `StepResult`
at all (never ran, or execution hasn't reached it yet), contributes
nothing to the answer -- silently excluded, not guessed at.

## How grounding actually works

`generate_answer` calls the LLM (Google's Gemini API, per
`docs/natural-language-planner.md`'s provider note) once, with a system
prompt that states
the boundary directly (never invent data, tag every claim with its
given category, say so plainly if the facts don't answer the question)
and a user message listing only the real facts assembled by
`_assemble_facts` -- the model sees nothing else. This is the actual
grounding mechanism: constraining what's *in the prompt* to only real,
already-computed values.

## Checking the answer after it is written

The prompt limits what the model sees, but it cannot stop the model
from writing a number anyway. `planner/groundedness.py` checks the text
after generation:

- Every number in the answer must match a number in the facts, their
  evidence, or the question, at the precision it was written with.
  "0.0123" must match exactly, "0.01" accepts anything that rounds to
  it, and "1.2%" is also compared as the fraction 0.012.
- Dates inside fact strings count, so "August 15, 2024" is supported by
  a `2024-08-15T10:00:00+00:00` cutoff.
- Signs are ignored, so a negative SHAP contribution can be written
  without its minus.
- Every `(observed)`, `(computed)`, `(predicted)` or `(documented)` tag
  must belong to a category some fact actually has.
- Every cited path, like `[docs/evaluation.md]`, must be one of the
  passages `search_docs` actually retrieved.

The result is returned with the answer as `grounding`
(`verified`, `checked`, `unsupported`, `unknown_tags`,
`unknown_citations`), and the web page
shows it under the answer. A failed check is shown as a warning rather
than hidden or silently rewritten.

The check is deliberately narrow. It catches invented or mis-copied
numbers, which is the failure that matters most here. It does not judge
whether a correctly copied number is used in the right sentence or
whether the wording is misleading.

With zero facts (an empty plan, or no step actually produced a
groundable result), `generate_answer` returns a fixed "cannot answer"
summary without calling the model at all -- there being nothing to
summarize, there is nothing to ask an LLM to write about, and
`tests/planner/test_generate_answer.py` proves this with a fake client
that fails the test if the model is ever invoked in that case.

## What this document does not define

Nothing here executes a plan or produces a real `StepResult` for a real
question -- that is the later workflow engine's job. There is no CLI script for this task
(unlike the natural-language planner's `run_planner_cli.py`): a real end-to-end demo needs a
real executed plan to summarize, which does not exist until that
workflow engine lands. Once it does, whatever calls that workflow engine to run a
validated `Plan` is also the natural caller of `generate_answer`, one
`StepResult` per completed step.
