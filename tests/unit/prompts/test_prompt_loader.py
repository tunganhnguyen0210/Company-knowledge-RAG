import pytest

from prompts.loader import load_prompt, render_user_template


def test_load_prompt_reads_packaged_yaml_definition() -> None:
    prompt = load_prompt("answer_v4.yaml")

    assert prompt.id == "answer"
    assert prompt.version == "v4"
    assert "CONTEXT" in prompt.user_template


def test_render_user_template_substitutes_supported_variables() -> None:
    rendered = render_user_template(
        "CONTEXT:\n{{ context }}\nQUESTION:\n{{ question }}",
        context="[C1] policy",
        question="Chính sách là gì?",
    )

    assert rendered == "CONTEXT:\n[C1] policy\nQUESTION:\nChính sách là gì?"


def test_render_user_template_rejects_unsupported_variable() -> None:
    with pytest.raises(ValueError, match="unsupported placeholder: answer"):
        render_user_template("{{ answer }}", context="context", question="question")
