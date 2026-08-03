from fastapi import HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from company_knowledge_rag.domain.schemas import Principal
from company_knowledge_rag.settings import Settings

api_key_header = APIKeyHeader(name="X-API-Key", scheme_name="ApiKeyAuth", auto_error=False)


def require_principal(
    request: Request, x_api_key: str | None = Security(api_key_header)
) -> Principal:
    if not x_api_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing X-API-Key")
    try:
        settings: Settings = request.app.state.settings
        return settings.principal_for_key(x_api_key)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid X-API-Key") from exc
