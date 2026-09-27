from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalCase:
    """A question about the system and the docs that answer it. A
    retrieval counts as a hit when any of `relevant` is among the
    retrieved sources. Questions are worded unlike the docs on purpose,
    so word overlap alone does not solve them."""

    question: str
    relevant: frozenset[str]


def _case(question: str, *sources: str) -> RetrievalCase:
    return RetrievalCase(
        question=question, relevant=frozenset(f"docs/{source}" for source in sources)
    )


RETRIEVAL_CASES: tuple[RetrievalCase, ...] = (
    _case(
        "How much better is the forecast model than the historical average?",
        "ml-benchmark.md",
        "evaluation.md",
        "headline-results.md",
    ),
    _case(
        "Do elevation and land cover improve predictions?",
        "ablation-benchmark.md",
        "headline-results.md",
    ),
    _case(
        "What happens to the work when a worker process dies halfway through?",
        "distributed-benchmark.md",
        "fault-injection-test.md",
    ),
    _case(
        "How are the predicted probabilities adjusted to match reality?",
        "ml-benchmark.md",
        "explainability.md",
    ),
    _case(
        "How big is each square of the map grid?",
        "california-grid-contract.md",
        "forecasting-specification.md",
    ),
    _case(
        "Which years were used to fit the model and which to test it?",
        "forecasting-specification.md",
        "scientific-regression-tests.md",
    ),
    _case(
        "Where does the satellite fire detection data come from?",
        "firms-input-contract.md",
    ),
    _case(
        "Which meteorological variables feed the model?",
        "era5-land-input-contract.md",
    ),
    _case(
        "Where do the terrain height and vegetation type layers come from?",
        "static-geography-input-contract.md",
    ),
    _case(
        "Can the language model run arbitrary code on the server?",
        "planner-tool-schemas.md",
        "plan-validator.md",
        "natural-language-planner.md",
        "security-baseline.md",
    ),
    _case(
        "What is checked about a plan before any step is executed?",
        "plan-validator.md",
    ),
    _case(
        "Which company's model turns questions into plans?",
        "natural-language-planner.md",
    ),
    _case(
        "How often does the planner understand questions correctly?",
        "planner-accuracy-benchmark.md",
        "planner-benchmark.md",
        "headline-results.md",
    ),
    _case("Do users need to log in to use the API?", "security-baseline.md"),
    _case(
        "How many requests can one client send before being throttled?",
        "security-baseline.md",
    ),
    _case(
        "What lifecycle states does a forecast job go through?",
        "forecast-async-jobs.md",
        "forecast-api-contract.md",
    ),
    _case(
        "What if the same forecast request is sent twice?",
        "forecast-retry-and-idempotency.md",
    ),
    _case(
        "How does the system recover a job that timed out?",
        "forecast-retry-and-idempotency.md",
        "reliability-tests.md",
    ),
    _case(
        "Is the system actually running on Amazon's cloud?",
        "terraform-layout.md",
        "cloud-deployment.md",
    ),
    _case(
        "How does the number of workers grow when jobs pile up?",
        "autoscaling.md",
    ),
    _case(
        "Does running more workers in parallel make it faster?",
        "multi-worker-scaling.md",
        "worker-replica-scaling.md",
        "bottleneck-identification.md",
        "distributed-benchmark.md",
    ),
    _case(
        "How can one request be followed across the backend and the worker?",
        "tracing.md",
    ),
    _case("Which operational numbers can be scraped for monitoring?", "metrics.md"),
    _case("What shape do the application log lines have?", "structured-logging.md"),
    _case("Which database tables hold forecasts?", "persistence-schema.md"),
    _case("Where are large output files kept?", "object-storage-contract.md"),
    _case(
        "How can someone rebuild all results starting from nothing?",
        "reproducibility-package.md",
        "clean-clone-test.md",
    ),
    _case("Which inputs push the risk score up the most?", "explainability.md"),
    _case(
        "How is a made-up number in the AI's reply caught?",
        "grounded-answer-generation.md",
    ),
    _case(
        "How well does the model work in areas it was not trained on?",
        "evaluation.md",
    ),
    _case(
        "Would assuming fires continue where they burned yesterday work as well?",
        "evaluation.md",
    ),
    _case(
        "How do you make sure future information never leaks into training?",
        "scientific-regression-tests.md",
        "forecasting-specification.md",
    ),
    _case(
        "Which containers start in the local setup?",
        "docker-compose-stack.md",
        "docker-images.md",
    ),
    _case(
        "How is the cluster run on a laptop?",
        "local-kubernetes-deployment.md",
        "kubernetes-manifests.md",
    ),
    _case(
        "What operations is the planner allowed to call?",
        "planner-tool-schemas.md",
    ),
)
