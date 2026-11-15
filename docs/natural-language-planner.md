# Natural-Language Planner

The planner turns a question in plain English into a validated plan.
It builds on `docs/planner-tool-schemas.md` and
`docs/plan-validator.md` and does not change either.

## Provider

The project design does not name an LLM provider, unlike the rest of
the stack. The planner used three providers during development:
Anthropic's Claude API, then OpenAI's API, and finally Google's Gemini
API (`gemini-3.1-flash-lite`, through
`client.models.generate_content` in the `google-genai` SDK). Gemini was
chosen for cost: its free tier needs no payment method, while the other
two are paid only. The placeholder in `.env.example` is
`GEMINI_API_KEY`, the variable that the `google-genai` SDK reads.

The flow below (LLM -> structured plan -> validator -> workflow) does
not depend on the provider. Each switch changed only the API call and
response parsing in `generate_plan` and `generate_answer`, not the
validator, the tools or the plan format.

## Flow

```text
natural language (a plain question string)
  -> generate_plan(question, client)
  -> client.models.generate_content(... config={"response_mime_type": "application/json", "response_schema": PLAN_OUTPUT_SCHEMA})
  -> one structured-output JSON document: {"steps": [{step_id, tool, input, depends_on}, ...]}
  -> parse_plan(question, payload) -> a Plan (the plan validator's dataclass)
  -> validate_plan_or_raise(plan)  (the plan validator, unchanged)
  -> a validated Plan, or ValueError
```

The planner makes one structured-output call, not a multi-turn
tool-calling loop. The order is LLM, then structured plan, then
validator, then workflow: the whole plan is produced once and checked
before anything runs. In a tool-calling loop, the model sees tool
results between turns, so some steps would already be running before a
later step existed, which means after the validator instead of before
it. This is also why the plan validator uses `$step_id.field` strings:
when the plan is written, nothing has run yet, so a dependent step
cannot hold an actual value.

## The LLM cannot skip the validator

`generate_plan` has only one return path, and it comes after
`validate_plan_or_raise(plan)` returns without an error. No branch
returns an unvalidated `Plan`, and no caller can skip the check.
`parse_plan` is public, for replaying a logged response, and returns a
plain `Plan`, but `generate_plan` never returns its output without
validating it first. An invalid plan raises `ValueError` from inside
`generate_plan`. Examples are an unknown tool name, input that does not
match the tool's schema, a bad region, time range or cutoff, and a
broken reference between steps. This is the same rejection that the
plan validator defines; there is no second, weaker check.

`PLAN_OUTPUT_SCHEMA` constrains only the top-level shape: `step_id`,
`tool` and `depends_on` are typed, and a step's `input` is any JSON
object. It does not describe each tool's input. That would need "the
shape of this field depends on the value of that other field", which
structured-output JSON Schema cannot express cleanly with
`oneOf`/`if`/`then`, and which LLM structured-output modes do not
support reliably. The per-tool check is `validate_plan` in the plan
validator, which runs after every LLM response. That is the reason for
a separate validator stage instead of trying to make the LLM's output
format perfect.

## The system prompt is generated

`_build_system_prompt()` builds each tool's name, description, input
schema and return shape from `planner.tools.TOOL_SCHEMAS`, the same
objects that the validator checks against. So the prompt cannot fall
out of step with the tools. `tests/planner/test_generate_plan.py` checks
that every tool name appears in it.

## Testing without API calls

`generate_plan` receives `client: genai.Client` as a parameter instead
of creating one. So `tests/planner/test_generate_plan.py` tests the
logic (the prompt sent, response parsing, the validator call, and
handling of a refusal or a response with no text) with a small fake
client and response. There is no network call, no API key and no cost.
A test still proves that the validator cannot be skipped: a fake
response with an unknown tool name raises `ValueError`.

The fake copies documented `google-genai` behavior. Reading a
response's `.text` property raises `ValueError` when there is no text
part, for example when a response is blocked for safety; there is no
separate refusal field to check first. `generate_plan` catches this
and raises its own "refused" `ValueError`.

`scripts/query/run_planner_cli.py` is the live entry point. It creates
a `genai.Client()` (which reads `GEMINI_API_KEY` from `.env` or the
environment) for trying a question end to end. Like the other scripts
under `scripts/`, it is not unit-tested.

## Out of scope

The planner does not run a plan. Running the steps (replacing
`$step_id.field` references with values and calling the Python
functions or the `/forecasts` API) is the job of the workflow engine.
Grounded answer generation then turns the results into a final answer
that separates observed, computed and predicted values. The planner
only gets from a question to a validated plan.
