# Spec: Golden Set Evaluation Enhancements

## Overview
Enhance the RAG evaluation runner and dataset to support ground-truth expected answers and negative abstention test cases.

## Requirements
1. **`expected_answer` Support**:
   - `GoldenCase` model in `src/evaluation/runner.py` must include `expected_answer: str | None = Field(default=None, validation_alias=AliasChoices("expected_answer", "answer"))`.
   - `run_golden_set` in `src/evaluation/runner.py` must include `expected_answer` in per-case output details dictionary when present.
2. **Negative Test Cases in `evaluation/golden_set.json`**:
   - Add negative test cases with `should_abstain: true`, an out-of-domain `question`, `expected_sources: []`, and `expected_answer: null` (or abstention message).
3. **Automated Verification**:
   - Unit tests in `tests/test_evaluation.py` to verify `GoldenCase` validation of `expected_answer` and `should_abstain`.
