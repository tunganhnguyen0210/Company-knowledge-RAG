# Coding Agent Guidelines & Testing Rules

## Testing Context Rules

1. Read tests/README.md before modifying tests.
2. Identify the affected source module before selecting test context.
3. Read the nearest existing tests before creating new tests.
4. Start with the smallest relevant test scope.
5. Classify new tests as unit or component.
6. Unit and component tests must not call live external services.
7. Qdrant is hosted on Qdrant Cloud; unit/component tests use MemoryChunkStore or fake providers.
8. Do not modify expected values only to make failing tests pass.
9. Do not modify golden-set data unless the task explicitly concerns evaluation.
10. Reuse tests/support only for stable repeated test concepts.
11. Do not create new generic test infrastructure without demonstrated duplication.
12. Report all commands executed.
13. Report tests that were not executed and explain why.
