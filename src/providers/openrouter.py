import instructor

from providers.base import (
    GenerationRequest,
    GenerationResult,
    ProviderError,
    StructuredResult,
    StructuredT,
)
from providers.openai import chat_completion_usage
from providers.structured import STRUCTURED_MAX_RETRIES, create_structured

TRANSIENT_STATUS_CODES = {408, 429, 500, 502, 503, 504}

# OpenRouter fronts many backends whose tool-calling and strict-schema support
# varies, so instructor carries the schema in the prompt and validates locally.
STRUCTURED_MODE = instructor.Mode.JSON


def is_transient_openrouter_error(exc: Exception) -> bool:
    status = getattr(exc, "status_code", 0)
    return status in TRANSIENT_STATUS_CODES or exc.__class__.__name__ in {
        "APIConnectionError",
        "APITimeoutError",
    }


class OpenRouterProvider:
    name = "openrouter"

    def __init__(
        self,
        api_key: str,
        model: str,
        allowed_models: set[str],
        timeout: float,
        structured_max_retries: int = STRUCTURED_MAX_RETRIES,
    ) -> None:
        if not api_key:
            raise ValueError("OpenRouter API key is required")
        if model not in allowed_models:
            raise ValueError("OpenRouter model is not allowlisted")
        from openai import OpenAI

        self.model = model
        self.structured_max_retries = structured_max_retries
        self._client = OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            timeout=timeout,
            max_retries=0,
        )
        self._structured_client = instructor.from_openai(self._client, mode=STRUCTURED_MODE)

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
                raise ProviderError("OpenRouter returned an empty response", transient=False)
            return GenerationResult(text, self.name, self.model, chat_completion_usage(response))
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(
                f"OpenRouter request failed: {exc}",
                transient=is_transient_openrouter_error(exc),
            ) from exc

    def generate_structured(
        self,
        request: GenerationRequest,
        response_model: type[StructuredT],
    ) -> StructuredResult[StructuredT]:
        value, completion = create_structured(
            self._structured_client,
            provider_name="OpenRouter",
            model=self.model,
            request=request,
            response_model=response_model,
            max_retries=self.structured_max_retries,
            is_transient=is_transient_openrouter_error,
            temperature=request.temperature,
            max_tokens=request.max_output_tokens,
        )
        return StructuredResult(value, self.name, self.model, chat_completion_usage(completion))

    def ready(self) -> bool:
        return bool(self._client and self.model)
