from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
import re

import yaml

_REQUIRED_FIELDS = ("id", "version", "system_instruction", "user_template")
_ALLOWED_PLACEHOLDERS = {"context", "question"}
_PLACEHOLDER_PATTERN = re.compile(r"{{\s*([^{}\s]+)\s*}}")


@dataclass(frozen=True)
class PromptDefinition:
    id: str
    version: str
    system_instruction: str
    user_template: str


def load_prompt(resource_name: str) -> PromptDefinition:
    resource = resources.files("company_knowledge_rag.prompts").joinpath(resource_name)
    raw: object = yaml.safe_load(resource.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"prompt {resource_name} must contain a mapping")

    values: dict[str, str] = {}
    for field in _REQUIRED_FIELDS:
        value = raw.get(field)
        if not isinstance(value, str):
            raise ValueError(f"prompt {resource_name} field {field} must be a string")
        values[field] = value

    render_user_template(values["user_template"], context="", question="")
    return PromptDefinition(**values)


def render_user_template(template: str, *, context: str, question: str) -> str:
    placeholders = set(_PLACEHOLDER_PATTERN.findall(template))
    unsupported = placeholders - _ALLOWED_PLACEHOLDERS
    if unsupported:
        placeholder = sorted(unsupported)[0]
        raise ValueError(f"unsupported placeholder: {placeholder}")
    return template.replace("{{ context }}", context).replace("{{ question }}", question)
