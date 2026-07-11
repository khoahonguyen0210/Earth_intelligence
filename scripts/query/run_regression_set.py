import json
from datetime import datetime, timezone
from pathlib import Path

from ai_earth_intelligence_and_forecasting_engine.query.regression_set import (
    REGRESSION_CASES,
    check_regression_case,
)

RAW_FIRMS_PATH = Path("data/raw/firms/firms_sample.csv")
REPORT_OUTPUT_PATH = Path("data/processed/regression/regression_report.json")


def main() -> None:
    case_results = []
    passed_count = 0

    for case in REGRESSION_CASES:
        passed, errors, response = check_regression_case(case, RAW_FIRMS_PATH)

        if passed:
            passed_count += 1

        case_results.append(
            {
                "name": case.name,
                "passed": passed,
                "errors": errors,
                "expected_intent": case.expected_intent,
                "expected_region_kind": case.expected_region_kind,
                "expected_operation": case.expected_operation,
                "expected_result_shape": case.expected_result_shape,
                "result": response["result"] if passed else None,
            }
        )

        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {case.name}")
        for error in errors:
            print(f"    - {error}")

    report = {
        "total_cases": len(REGRESSION_CASES),
        "passed_cases": passed_count,
        "failed_cases": len(REGRESSION_CASES) - passed_count,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cases": case_results,
    }

    REPORT_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_OUTPUT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"\n{passed_count}/{len(REGRESSION_CASES)} cases passed")
    print(f"Saved regression report to: {REPORT_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
