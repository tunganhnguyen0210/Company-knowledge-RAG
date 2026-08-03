from fastapi import Header, HTTPException, Request, status

from company_knowledge_rag.domain.schemas import Principal
from company_knowledge_rag.settings import Settings


def require_principal(request: Request, x_api_key: str | None = Header(default=None)) -> Principal:
    if not x_api_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing X-API-Key")
    try:
        settings: Settings = request.app.state.settings
        return settings.principal_for_key(x_api_key)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid X-API-Key") from exc
