from openai import OpenAI

from providers.base import GenerationRequest, GenerationResult, ProviderError

TRANSIENT_STATUS_CODES = {408, 429, 500, 502, 503, 504}


def is_transient_openai_error(exc: Exception) -> bool:
    status = getattr(exc, "status_code", 0)
    return status in TRANSIENT_STATUS_CODES or exc.__class__.__name__ in {
        "APIConnectionError",
        "APITimeoutError",
    }


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str, model: str, timeout: float) -> None:
        if not api_key:
            raise ValueError("OpenAI API key is required")
        self.model = model
        self._client = OpenAI(api_key=api_key, timeout=timeout, max_retries=0)

    def generate(self, request: GenerationRequest) -> GenerationResult:
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": request.system_instruction},
                    {"role": "user", "content": request.user_prompt},
                ],
                temperature=request.temperature,
                max_tokens=request.max_output_tokens,
            )
            text = response.choices[0].message.content or ""
            if not text:
                raise ProviderError("OpenAI returned an empty response", transient=False)
            usage = {
                "input_tokens": int(getattr(response.usage, "prompt_tokens", 0) or 0),
                "output_tokens": int(getattr(response.usage, "completion_tokens", 0) or 0),
            }
            return GenerationResult(text, self.name, self.model, usage)
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(
                f"OpenAI request failed: {exc}", transient=is_transient_openai_error(exc)
            ) from exc

    def ready(self) -> bool:
        return bool(self._client and self.model)
