# YAML-backed Answer Prompts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Store `answer_v1` in validated YAML without changing callers of `render_answer_prompt()`.

**Architecture:** A loader reads package-local YAML with `yaml.safe_load`, validates a fixed schema, and renders only `{{ context }}` and `{{ question }}`. `answer_v1.py` remains a small compatibility facade that builds trusted citation-formatted context.

**Tech Stack:** Python 3.11, PyYAML, `importlib.resources`, pytest, Hatchling.

## Global Constraints

- YAML fields `id`, `version`, `system_instruction`, and `user_template` must be strings.
- Only `{{ context }}` and `{{ question }}` are legal template placeholders.
- Use `yaml.safe_load`; no template expression evaluation.
- Keep `render_answer_prompt(question: str, chunks: list[Chunk]) -> RenderedPrompt` and `PROMPT_VERSION == "answer_v1"`.
- Do not stage or modify untracked `data/seed/` files.

---

### Task 1: Implement a validated YAML loader

**Files:**
- Create: `src/company_knowledge_rag/prompts/loader.py`
- Create: `src/company_knowledge_rag/prompts/answer_v1.yaml`
- Create: `tests/test_prompt_loader.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Produces `PromptDefinition(id: str, version: str, system_instruction: str, user_template: str)`.
- Produces `load_prompt(resource_name: str) -> PromptDefinition`.
- Produces `render_user_template(template: str, *, context: str, question: str) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
from company_knowledge_rag.prompts.loader import load_prompt, render_user_template


def test_load_prompt_reads_packaged_yaml_definition() -> None:
    prompt = load_prompt("answer_v1.yaml")
    assert (prompt.id, prompt.version) == ("answer", "v1")


def test_render_user_template_substitutes_supported_variables() -> None:
    rendered = render_user_template(
        "CONTEXT:\n{{ context }}\nQUESTION:\n{{ question }}",
        context="[C1] policy",
        question="Chính sách là gì?",
    )
    assert rendered == "CONTEXT:\n[C1] policy\nQUESTION:\nChính sách là gì?"
```

- [ ] **Step 2: Verify RED**

Run: `pytest tests/test_prompt_loader.py -v`

Expected: collection fails because `company_knowledge_rag.prompts.loader` does not exist.

- [ ] **Step 3: Implement the minimum loader**

Add `"PyYAML>=6,<7"` to production dependencies. Use this exact public API:

```python
@dataclass(frozen=True)
class PromptDefinition:
    id: str
    version: str
    system_instruction: str
    user_template: str

def load_prompt(resource_name: str) -> PromptDefinition: ...
def render_user_template(template: str, *, context: str, question: str) -> str: ...
```

Use `importlib.resources.files("company_knowledge_rag.prompts").joinpath(resource_name)` and `yaml.safe_load`. Raise `ValueError` for a non-mapping document, absent/non-string required fields, or unsupported `{{ name }}` placeholders. Render via two direct `str.replace` calls, never dynamic evaluation.

- [ ] **Step 4: Verify GREEN**

Run: `pytest tests/test_prompt_loader.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/company_knowledge_rag/prompts/loader.py tests/test_prompt_loader.py
git commit -m "feat: add YAML prompt loader"
```

### Task 2: Migrate answer_v1 and retain its API

**Files:**
- Modify: `src/company_knowledge_rag/prompts/answer_v1.py`
- Modify: `tests/test_prompt.py`

**Interfaces:**
- Consumes `load_prompt("answer_v1.yaml")` and `render_user_template()` from Task 1.
- Produces unchanged `PROMPT_VERSION`, `RenderedPrompt`, and `render_answer_prompt()`.

- [ ] **Step 1: Write the failing migration test**

```python
def test_answer_prompt_uses_versioned_yaml_system_and_user_template() -> None:
    chunk = Chunk(..., text="VPN chỉ dành cho nhân viên.", ...)
    prompt = render_answer_prompt("Ai được dùng VPN?", [chunk])
    assert PROMPT_VERSION == "answer_v1"
    assert "CONTEXT" in prompt.user_prompt
    assert "QUESTION" in prompt.user_prompt
    assert "[C1]" in prompt.user_prompt
    assert "untrusted" in prompt.system_instruction.lower()
```

Use the complete inline `Chunk` construction pattern already in `tests/test_prompt.py`; preserve its existing adversarial-context test.

- [ ] **Step 2: Verify RED**

Run: `pytest tests/test_prompt.py::test_answer_prompt_uses_versioned_yaml_system_and_user_template -v`

Expected: FAIL because the named test and YAML resource do not yet exist.

- [ ] **Step 3: Create YAML and adapt the facade**

Create this resource shape, preserving every existing Vietnamese policy line under `system_instruction`:

```yaml
id: answer
version: v1
system_instruction: |
  Bạn là trợ lý hỏi đáp tài liệu nội bộ.
user_template: |
  CONTEXT:
  {{ context }}

  QUESTION:
  {{ question }}
```

Load it once in `answer_v1.py`; set `PROMPT_VERSION = f"{definition.id}_{definition.version}"`. Keep `RenderedPrompt`. Build `[C<n>] source=... version=...` context exactly as today, then call `render_user_template`.

- [ ] **Step 4: Verify GREEN**

Run: `pytest tests/test_prompt.py tests/test_prompt_loader.py -v`

Expected: PASS, including citation and untrusted-context checks.

- [ ] **Step 5: Commit**

```bash
git add src/company_knowledge_rag/prompts/answer_v1.py src/company_knowledge_rag/prompts/answer_v1.yaml tests/test_prompt.py
git commit -m "feat: move answer prompt to YAML"
```

### Task 3: Verify full packaging and regression behavior

**Files:**
- Modify: `pyproject.toml` only if the wheel omits `answer_v1.yaml`.
- Test: `tests/test_prompt_loader.py`

**Interfaces:**
- Consumes the Task 1 loader and Task 2 resource.
- Produces a wheel containing `company_knowledge_rag/prompts/answer_v1.yaml`.

- [ ] **Step 1: Run the complete unit suite**

Run: `pytest`

Expected: PASS with no failures.

- [ ] **Step 2: Build and inspect the wheel**

Run: `python -m pip wheel --no-deps --wheel-dir .tmp-wheel .`

Run: `python -c "import pathlib,zipfile; w=next(pathlib.Path('.tmp-wheel').glob('*.whl')); assert any(n.endswith('prompts/answer_v1.yaml') for n in zipfile.ZipFile(w).namelist())"`

Expected: both commands exit 0. If the assertion fails, add the minimal Hatchling include rule, then rerun both commands.

- [ ] **Step 3: Run static checks**

Run: `ruff check src tests && mypy src`

Expected: both commands exit 0.

- [ ] **Step 4: Commit only required packaging configuration**

```bash
git add pyproject.toml
git commit -m "build: package YAML prompt resources"
```

Do not create this commit when packaging configuration is unchanged.
