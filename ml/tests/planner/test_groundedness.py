from __future__ import annotations

from ai_earth_intelligence_and_forecasting_engine.planner.groundedness import (
    check_grounding,
)

FORECAST_FACT = (
    "predicted",
    {
        "result": {
            "max_probability": 0.0123,
            "mean_probability": 0.0021,
            "cell_count": 1854,
            "data_cutoff": "2024-08-15T10:00:00+00:00",
            "forecast_window": {"hours": 24},
            "drivers": [{"feature": "previous_7d_count", "contribution": -0.4182}],
        },
        "evidence": None,
    },
)
COUNT_FACT = ("computed", {"result": {"count": 1234}, "evidence": None})


def test_numbers_copied_from_the_facts_are_verified():
    answer = (
        "Across 1,854 cells (predicted) the highest 24-hour risk is 0.0123 "
        "(predicted), made as of 2024-08-15T10:00:00+00:00."
    )

    check = check_grounding(answer, [FORECAST_FACT])

    assert check.verified
    assert check.unsupported == ()
    assert check.checked >= 3


def test_a_probability_written_as_a_rounded_percentage_is_verified():
    check = check_grounding("Peak risk is about 1.2% (predicted).", [FORECAST_FACT])

    assert check.verified


def test_a_number_that_appears_nowhere_is_flagged():
    check = check_grounding(
        "There were 1,300 fires (computed) and peak risk is 0.0123 (predicted).",
        [COUNT_FACT, FORECAST_FACT],
    )

    assert not check.verified
    assert check.unsupported == ("1,300",)


def test_rounding_beyond_the_written_precision_is_flagged():
    check = check_grounding("Peak risk is 0.02 (predicted).", [FORECAST_FACT])

    assert check.unsupported == ("0.02",)


def test_numbers_echoed_from_the_question_are_allowed():
    check = check_grounding(
        "In August 2024 there were 1,234 detections (computed).",
        [COUNT_FACT],
        question="How many wildfires were there in August 2024?",
    )

    assert check.verified


def test_a_negative_contribution_may_be_written_without_its_sign():
    check = check_grounding(
        "Recent fire activity lowered the score by 0.42 (predicted).",
        [FORECAST_FACT],
    )

    assert check.verified


def test_a_category_tag_no_fact_carries_is_reported():
    check = check_grounding("There were 1,234 fires (observed).", [COUNT_FACT])

    assert not check.verified
    assert check.unknown_tags == ("observed",)


DOCS_FACT = (
    "documented",
    {
        "result": {
            "query": "is there a login",
            "passages": [
                {
                    "source": "docs/security-baseline.md",
                    "heading": "Authentication",
                    "text": (
                        "The API has no user authentication. "
                        "It allows 20 requests per minute."
                    ),
                    "score": 0.03,
                }
            ],
        },
        "evidence": None,
    },
)


def test_a_cited_retrieved_doc_with_its_number_is_verified():
    check = check_grounding(
        "There is no login, and clients get 20 requests per minute (documented) "
        "[docs/security-baseline.md].",
        [DOCS_FACT],
    )

    assert check.verified
    assert check.unknown_citations == ()


def test_citing_a_doc_that_was_not_retrieved_is_flagged():
    check = check_grounding(
        "There is no login (documented) [docs/cloud-deployment.md].", [DOCS_FACT]
    )

    assert not check.verified
    assert check.unknown_citations == ("docs/cloud-deployment.md",)


def test_an_answer_without_numbers_checks_nothing_and_passes():
    check = check_grounding("The facts do not answer this question.", [COUNT_FACT])

    assert check.verified
    assert check.checked == 0
