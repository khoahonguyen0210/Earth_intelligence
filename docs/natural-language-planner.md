# Natural-Language Planner — LOCKED

This document freezes the natural-language planner per Task 7.3 of the
Execution Handbook. It is not a brainstorming document. It builds on
`docs/planner-tool-schemas.md` (Task 7.1) and `docs/plan-validator.md`
(Task 7.2) rather than redefining either.

## Provider

The locked project contract does not fix an LLM provider (unlike every
other stack choice). This implementation went through three providers
before landing: Anthropic's Claude API, then OpenAI's API, then Google's
Gemini API (`gemini-3.1-flash-lite`, via the `google-genai` SDK's
`client.models.generate_content`) -- the final choice, made for cost
reasons (Gemini's free tier needs no payment method, unlike either
paid-only alternative). `.env.example`'s placeholder is `GEMINI_API_KEY`,
the variable the `google-genai` SDK reads. Nothing about the flow below
(LLM -> structured plan -> validator -> workflow) is provider-specific:
swapping providers only touched `generate_plan`/`generate_answer`'s API
call and response parsing, not the validator, the tool surface, or the
plan shape.

## The flow, concretely

```text
natural language (a plain question string)
  -> generate_plan(question, client)
  -> client.models.generate_content(... config={"response_mime_type": "application/json", "response_schema": PLAN_OUTPUT_SCHEMA})
  -> one structured-output JSON document: {"steps": [{step_id, tool, input, depends_on}, ...]}
  -> parse_plan(question, payload) -> a Plan (Task 7.2's dataclass)
  -> validate_plan_or_raise(plan)  -- Task 7.2, unmodified
  -> a validated Plan, or ValueError
```

One structured-output call, not a live multi-turn tool-calling loop:
`docs/PROMPT_SYSTEM.md`'s flow is "LLM -> structured plan -> validator ->
workflow" -- the whole plan is produced once, then validated, before
anything executes. A live tool-use loop (where the model sees real tool
results between turns) doesn't fit that ordering, since by the time a
later step's real dependency value existed, execution would already be
underway -- past the validator, not before it. This is also why Task
7.2's `$step_id.field` string convention exists: at plan-authoring time,
nothing has executed yet, so a dependent step's value cannot be a real
one.

## The LLM cannot bypass the validator

`generate_plan` has exactly one return path, and it is after
`validate_plan_or_raise(plan)` returns without raising. There is no
branch that hands back an unvalidated `Plan`, and no caller has a way to
skip the check -- `parse_plan` (public, for replaying a logged response)
returns a plain `Plan`, but `generate_plan` itself never returns what
`parse_plan` produced without validating it first. An invalid plan --
wrong tool name, input that doesn't match that tool's schema, a bad
region/time range/cutoff, or a broken cross-step reference -- raises
`ValueError` from inside `generate_plan`, the same rejection Task 7.2
already defined; this task adds no second, weaker enforcement path.

`PLAN_OUTPUT_SCHEMA` itself only constrains shape at the top level
(`step_id`/`tool`/`depends_on` are typed; a step's `input` is a bare
JSON object) -- it does not attempt to encode "this tool's input must
look like X" per tool, because JSON Schema's structured-output mode
cannot cleanly express "the shape of this field depends on the value of
that sibling field" the way `oneOf`/`if`/`then` would need to, and
LLM structured-output implementations do not reliably support that. The
real per-tool enforcement is Task 7.2's `validate_plan`, run
unconditionally after every LLM response, which is the actual point of
having a separate validator stage rather than trying to make the LLM's
own output format airtight.

## The system prompt is generated, not hand-written

`_build_system_prompt()` renders each tool's name, description, input
schema, and return shape directly from `planner.tools.TOOL_SCHEMAS` (the
same Task 7.1 objects the validator checks against), so the prompt
cannot silently drift out of sync with the real tool surface --
`tests/planner/test_generate_plan.py` checks every tool name appears in
it.

## Testing without spending real API calls

`generate_plan` takes `client: genai.Client` as a parameter rather than
constructing one internally, so `tests/planner/test_generate_plan.py`
exercises the real orchestration logic (prompt sent, response parsed,
validator invoked, refusal/no-text-block handling) against a small fake
client/response -- no network call, no API key, no cost -- while still
proving the "cannot bypass the validator" property with a concrete test
(a fake response containing an unknown tool name raises `ValueError`).
The fake mirrors a real, documented `google-genai` behavior: accessing a
response's `.text` property itself raises `ValueError` when there is no
text part (e.g. a safety-blocked response), rather than exposing a
separate refusal field to check first -- that is what `generate_plan`
catches and re-raises as its own "refused" `ValueError`.
`scripts/query/run_planner_cli.py` is the actual live entry point,
constructing a real `genai.Client()` (`GEMINI_API_KEY` auto-resolved
from `.env` or the real environment) for anyone who wants to try a real
question end to end; it is intentionally not unit-tested itself, the
same treatment every other real-caller script under `scripts/` already
gets.

## What this document does not define

Nothing here executes a validated plan -- turning a `Plan`'s steps into
real tool calls (resolving `$step_id.field` references to actual values,
calling the real Python functions or the real `/forecasts` API) is
Phase 8's workflow engine, not this task. Task 7.4 (grounded answer
generation) is what turns an executed plan's results back into a
final answer distinguishing observed/computed/predicted; this task only
gets from a question to a validated plan.
