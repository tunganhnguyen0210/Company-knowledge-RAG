from __future__ import annotations

from providers.base import GenerationProvider, GenerationRequest

HYDE_SYSTEM = (
    "Bạn là chuyên gia pháp lý Việt Nam. "
    "Viết 1 đoạn văn ngắn (3-5 câu) trả lời trực tiếp câu hỏi sau "
    "như thể đang trích dẫn từ một văn bản pháp lý chính thức. "
    "Chỉ trả về đoạn văn, không giải thích thêm."
)

MULTI_QUERY_SYSTEM = (
    "Sinh {n} cách diễn đạt khác nhau cho câu hỏi pháp lý sau. "
    "Mỗi cách trên một dòng, không đánh số. "
    "Giữ nguyên ý định gốc, thay đổi từ ngữ và cấu trúc câu."
)


class QueryTransformer:
    """Stateless — không giữ state, thread-safe."""

    def hyde(self, query: str, provider: GenerationProvider) -> str:
        """
        Trả về hypothetical document text để embed cho Dense search.
        Fallback: LLM fail hoặc trả chuỗi rỗng → trả về raw query.
        """
        try:
            result = provider.generate(
                GenerationRequest(
                    system_instruction=HYDE_SYSTEM,
                    user_prompt=query,
                    temperature=0.3,
                    max_output_tokens=300,
                )
            )
            return result.text.strip() or query
        except Exception:
            return query

    def expand(
        self,
        query: str,
        provider: GenerationProvider,
        n: int = 3,
    ) -> list[str]:
        """
        Trả về [raw_query] + n paraphrases.
        raw_query luôn ở index 0 — là fallback khi LLM fail.
        """
        try:
            result = provider.generate(
                GenerationRequest(
                    system_instruction=MULTI_QUERY_SYSTEM.format(n=n),
                    user_prompt=query,
                    temperature=0.5,
                    max_output_tokens=400,
                )
            )
            paraphrases = [
                line.strip()
                for line in result.text.strip().splitlines()
                if line.strip() and line.strip() != query
            ][:n]
            return [query] + paraphrases
        except Exception:
            return [query]
