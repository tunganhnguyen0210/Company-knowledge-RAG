# Staged Offline RAG Evaluation Plan Review Delegation

## Reviewer assignment

Review the implementation plan at:

- `docs/superpowers/plans/2026-08-05-staged-offline-rag-evaluation.md`

Follow the complete reviewer goals, authority order, review hotspots, severity definitions, and acceptance criteria in:

- `docs/superpowers/handoffs/2026-08-05-staged-offline-rag-evaluation-plan-review.md`

The review is read-only. Do not implement the plan, change approved scope, ingest data, call a paid judge, stage files, or commit unrelated work.

## Mandatory saved deliverable

Save the complete review report to this exact path:

- `docs/superpowers/handoffs/2026-08-05-staged-offline-rag-evaluation-plan-review-report.md`

The report must contain:

1. findings ordered by P0, P1, then P2;
2. the exact plan task/step and symbol or command for every finding;
3. the violated authority or invariant;
4. a concrete correction;
5. whether the correction changes approved scope;
6. a final verdict of `APPROVE`, `APPROVE WITH P2`, or `REVISE`;
7. explicit P0/P1/P2 counts.

If there are no findings, state that explicitly. Do not invent stylistic findings.

After saving the report, return only a concise status message containing the saved report path, verdict, and P0/P1/P2 counts. The repository report is the required continuation checkpoint for the next agent.
