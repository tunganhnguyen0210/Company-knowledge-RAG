# Project Constitution

## Core Principles

1. **Deterministic Evaluation**: All Layer-1 regression checks must be deterministic, reproducible, and fast.
2. **Schema Resilience**: Pydantic models must robustly handle field aliases (`answer` -> `expected_answer`, `source` -> `expected_sources`).
3. **Comprehensive Test Coverage**: Unit tests must validate dataset parsing, metric calculations, and edge cases.
4. **Non-Destructive Enhancements**: Dataset additions must preserve existing test cases and format standards.
