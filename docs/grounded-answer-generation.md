# Grounded Answer Generation — LOCKED

This document freezes grounded answer generation per Task 7.4 of the
Execution Handbook, the last task of Phase 7. It is not a brainstorming
document. It builds on `docs/plan-validator.md` (Task 7.2) and
`docs/natural-language-planner.md` (Task 7.3) rather than redefining
either.

## Scope: this task consumes execution results, it does not produce them

"The final answer can summarize only execution results + evidence"
presupposes those results already exist. Actually executing a validated
`Plan` -- turning each step into a real tool call, resolving
`$step_id.field` references to real values -- is Phase 8's workflow
engine, a later, separate set of tasks (DAG schema, state machine,
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

This is the minimal shape Task 7.4 needs, not a preview of Phase 8's
real result type. `tests/planner/test_generate_answer.py` never
fabricates a `StepResult`'s `result`/`evidence` by hand-typing a
plausible-looking dict -- every test builds one from genuine calls to
the real Task 2.4/2.6 functions (`query.statistics.count`,
`query.evidence.build_evidence`), so the fixtures are real values, not
guesses at what those functions might return.

## observed / computed / predicted

```python
RESULT_CATEGORY_BY_TOOL = {
    "get_data": "observed",
    "calculate_statistics": "computed",
    "generate_map": "computed",
    "run_forecast": "predicted",
}
```

Only four of the six tools appear. `resolve_region` is absent: it
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
already-computed values, not a post-hoc check on what the model wrote.
There is no automated verification that the returned text only restates
the given facts (unlike Task 7.2's plan validator, there is no
"answer validator" task in the handbook for this stage) -- accepted as
a real, honestly-documented limitation rather than something silently
assumed solved.

With zero facts (an empty plan, or no step actually produced a
groundable result), `generate_answer` returns a fixed "cannot answer"
summary without calling the model at all -- there being nothing to
summarize, there is nothing to ask an LLM to write about, and
`tests/planner/test_generate_answer.py` proves this with a fake client
that fails the test if the model is ever invoked in that case.

## What this document does not define

Nothing here executes a plan or produces a real `StepResult` for a real
question -- that is Phase 8's job. There is no CLI script for this task
(unlike Task 7.3's `run_planner_cli.py`): a real end-to-end demo needs a
real executed plan to summarize, which does not exist until Phase 8
lands. Once it does, whatever calls Phase 8's workflow engine to run a
validated `Plan` is also the natural caller of `generate_answer`, one
`StepResult` per completed step.
