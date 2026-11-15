# Grounded Answer Generation

`generate_answer` turns the results of an executed plan into a final
answer. It builds on `docs/plan-validator.md` and
`docs/natural-language-planner.md` and does not change either.

## Scope: it uses results, it does not produce them

The final answer may summarize only execution results and their
evidence, so those results must already exist. Running a validated
`Plan`, which means turning each step into a tool call and replacing
`$step_id.field` references with values, is the job of the workflow
engine (DAG schema, state machine, execution and persistence).
`generate_answer` does not run anything.

So it takes execution results as input:

```python
@dataclass(frozen=True)
class StepResult:
    step_id: str
    tool: str
    result: Any
    evidence: dict[str, Any] | None = None
```

This is the smallest shape needed here. `tests/planner/test_generate_answer.py`
never types a `result` or `evidence` dictionary by hand. Every test
builds one by calling the underlying functions
(`query.statistics.count`, `query.evidence.build_evidence`), so the
fixtures hold values those functions actually return.

## Observed, computed, predicted

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

Six of the eight tools appear. A `documented` fact is a passage from
`docs/`, and the answer must cite each one it uses by its path.
`resolve_region` is left out because it resolves a geometry and does
not produce a fact worth stating. `get_result_evidence` is left out
because it fetches information about a fact that another step already
produced; it is not a fact itself. A step whose tool is not in this
table, or that has no `StepResult` (it never ran, or execution has not
reached it), adds nothing to the answer. It is left out, not guessed.

## How grounding works

`generate_answer` calls the LLM (Google's Gemini API, see the provider
note in `docs/natural-language-planner.md`) once. The system prompt
states the rules: never invent data, tag every claim with its category,
and say plainly when the facts do not answer the question. The user
message lists only the facts assembled by `_assemble_facts`, and the
model sees nothing else. Limiting the prompt to values that were
already computed is how the answer is grounded.

## Checking the answer after it is written

The prompt limits what the model sees, but it cannot stop the model
from writing a number anyway. `planner/groundedness.py` checks the text
after it is generated:

- Every number in the answer must match a number in the facts, their
  evidence or the question, at the precision it was written with.
  "0.0123" must match exactly, "0.01" accepts anything that rounds to
  it, and "1.2%" is also compared as the fraction 0.012.
- Dates inside fact strings count, so "August 15, 2024" is supported by
  a `2024-08-15T10:00:00+00:00` cutoff.
- Signs are ignored, so a negative SHAP contribution can be written
  without its minus sign.
- Every `(observed)`, `(computed)`, `(predicted)` or `(documented)` tag
  must belong to a category that some fact has.
- Every cited path, like `[docs/evaluation.md]`, must be one of the
  passages that `search_docs` retrieved.

The result comes back with the answer as `grounding` (`verified`,
`checked`, `unsupported`, `unknown_tags`, `unknown_citations`), and the
web page shows it under the answer. A failed check is shown as a
warning; it is not hidden or quietly rewritten.

The check is narrow on purpose. It catches invented or wrongly copied
numbers, which is the most important failure here. It does not judge
whether a correctly copied number is used in the right sentence, or
whether the wording is misleading.

With no facts (an empty plan, or no step produced a result that can be
grounded), `generate_answer` returns a fixed "cannot answer" summary
without calling the model. With nothing to summarize, there is nothing
to ask an LLM to write. `tests/planner/test_generate_answer.py` checks
this with a fake client that fails the test if the model is called.

## Where it is used

`generate_answer` does not run plans. The Ask Earth pipeline
(`docs/ask-earth.md`) runs a validated `Plan` with `execute_plan` and
then passes one `StepResult` per finished step to `generate_answer`.
