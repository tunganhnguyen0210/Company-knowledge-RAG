from dataclasses import dataclass

from domain.schemas import Chunk
from prompts.loader import load_prompt, render_user_template

_PROMPT = load_prompt("answer.yaml")
PROMPT_VERSION = f"{_PROMPT.id}_{_PROMPT.version}"


@dataclass(frozen=True)
class RenderedPrompt:
    system_instruction: str
    user_prompt: str


def render_answer_prompt(question: str, chunks: list[Chunk]) -> RenderedPrompt:
    context = "\n\n".join(
        f"[C{index}] source={chunk.source_name} version={chunk.version}"
        # Without the section the model cannot name the article a passage came from,
        # because the chunk text itself may start in the middle of one.
        f"{f' section={chunk.section}' if chunk.section else ''}\n{chunk.text}"
        for index, chunk in enumerate(chunks, start=1)
    )
    return RenderedPrompt(
        system_instruction=_PROMPT.system_instruction,
        user_prompt=render_user_template(_PROMPT.user_template, context=context, question=question),
    )
