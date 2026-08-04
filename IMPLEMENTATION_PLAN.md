# Implementation Plan: Golden Set Evaluation Enhancements

## Tasks

- [x] **Task 1: Add `expected_answer` to `GoldenCase` in `src/evaluation/runner.py`**
  - Files: `src/evaluation/runner.py`
  - Validation: `uv run pytest tests/test_evaluation.py`
  - Acceptance Criteria: `GoldenCase.model_validate({"answer": "baseline text"})` sets `expected_answer == "baseline text"`. Output report details include `"expected_answer"`.

- [x] **Task 2: Add negative (abstention) test cases to `evaluation/golden_set.json`**
  - Files: `evaluation/golden_set.json`
  - Validation: `uv run pytest tests/test_evaluation.py`
  - Acceptance Criteria: `golden_set.json` contains test cases with `should_abstain: true`.

- [x] **Task 3: Add unit tests for `expected_answer` and negative test case parsing**
  - Files: `tests/test_evaluation.py`
  - Validation: `uv run pytest tests/test_evaluation.py`
  - Acceptance Criteria: All unit tests in `tests/test_evaluation.py` pass.
