# Wayfinder Map: Test Suite Maintenance & Governance Spec

## Destination

A complete `Test Suite Maintenance & Governance Spec` saved at [`docs/superpowers/specs/2026-08-05-test-suite-governance-and-maintenance-spec.md`](file:///E:/VIN-INTERNSHIP/Cowork-RAG/docs/superpowers/specs/2026-08-05-test-suite-governance-and-maintenance-spec.md) establishing strict source-to-test mirroring rules, parametrization standards, stale test pruning workflows, assertion depth criteria, and static dead-code/dead-fixture analysis (`vulture` / `pytest-deadfixtures`) integration.

## Notes

- **Domain**: Test Engineering, Codebase Quality & CI Governance
- **References & Context**: 
  - [`tests/README.md`](file:///E:/VIN-INTERNSHIP/Cowork-RAG/tests/README.md)
  - [`docs/superpowers/handoffs/2026-08-05-test-suite-management-and-stale-test-pruning.md`](file:///E:/VIN-INTERNSHIP/Cowork-RAG/docs/superpowers/handoffs/2026-08-05-test-suite-management-and-stale-test-pruning.md)
  - [`AGENTS.md`](file:///E:/VIN-INTERNSHIP/Cowork-RAG/AGENTS.md)
- **Standing Preferences**:
  - Flexible speed budget prioritizing assertion depth over execution speed.
  - Zero live external calls in unit/component tests; enforce shared test doubles under `tests/support/`.

---

## Decisions so far

- **[Ticket 1: Static Dead-Code & Dead-Fixture Tooling Configuration]** — Standardized `pyproject.toml` `[tool.vulture]` settings (`min_confidence = 80`, `ignore_decorators`, `ignore_names`) and `pytest --dead-fixtures` execution flags.
- **[Ticket 2: Parametrization & Shared Builder Adoption Standards]** — Mandated `@pytest.mark.parametrize` for 2+ input variations on the same contract, and required mandatory reuse of `make_chunk` and `tests/support/providers.py` fakes.
- **[Ticket 3: Stale Test Pruning & Deprecation Lifecycle Rules]** — Enforced same-commit deletion of matching test files when `src/` modules are sunsetted, mandatory symbol import audits, and `tests/README.md` index sync.
- **[Ticket 4: Assertion Depth & Anti-Superficiality Guidelines]** — Explicitly prohibited superficial `assert x is not None` checks; mandated strict contract/field value assertions per module layer.

---

## Frontier Tickets (Open & Unblocked)

- [x] **[Ticket 1: Static Dead-Code & Dead-Fixture Tooling Configuration]** (`wayfinder:research`)
  - **Question**: How should `vulture` and `pytest-deadfixtures` be configured in `pyproject.toml` with appropriate whitelist/ignore rules so that legitimate pytest fixtures, hooks, and test parameters are not falsely flagged?
  - **Status**: Closed (Resolved)

- [x] **[Ticket 2: Parametrization & Shared Builder Adoption Standards]** (`wayfinder:grilling`)
  - **Question**: What are the exact threshold criteria for when tests MUST use `@pytest.mark.parametrize` instead of individual test functions, and how do we enforce usage of `tests/support/builders.py` and `tests/support/providers.py`?
  - **Status**: Closed (Resolved)

- [x] **[Ticket 3: Stale Test Pruning & Deprecation Lifecycle Rules]** (`wayfinder:task`)
  - **Question**: What step-by-step process and verification rules govern deleting or merging orphaned test files when production modules in `src/` are refactored or deleted?
  - **Status**: Closed (Resolved)

- [x] **[Ticket 4: Assertion Depth & Anti-Superficiality Guidelines]** (`wayfinder:grilling`)
  - **Question**: What assertion standards will prevent superficial coverage (e.g., `assert x is not None`) and mandate exact value/contract assertions for domain, ingestion, generation, and API modules?
  - **Status**: Closed (Resolved)

---

## Not yet specified

- **CI & Pre-Commit Quality Gate Integration**: How to wire `vulture` and `pytest-deadfixtures` checks into pre-commit configuration or GitHub Actions once tool rules are finalized.
- **Package-Specific Coverage Threshold Enforcements**: Setting minimal per-package `--cov` thresholds in `pyproject.toml` after baseline suite cleanup.

---

## Out of scope

- **Live External Service Integration Testing**: Calling live Qdrant Cloud, Gemini, Jina, or OpenAI APIs in unit/component tests (forbidden by [`AGENTS.md`](file:///E:/VIN-INTERNSHIP/Cowork-RAG/AGENTS.md)).
- **Hard Speed Limits (< 30s)**: Imposing strict execution time caps that sacrifice assertion thoroughness.
