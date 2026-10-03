from fastapi import APIRouter, Depends

from app.api.deps import current_user
from app.core.config import get_settings
from app.services.rag.retrieval_profiles import (
    RetrievalProfileCatalog,
    RetrievalProfileStatus,
    build_profile_catalog,
    build_profile_status,
)

router = APIRouter(prefix="/retrieval", tags=["retrieval profiles"])


@router.get("/profiles", response_model=RetrievalProfileCatalog)
async def list_retrieval_profiles(user=Depends(current_user)) -> RetrievalProfileCatalog:
    del user
    return build_profile_catalog(get_settings().embedding_model)


@router.get("/status", response_model=RetrievalProfileStatus)
async def retrieval_profile_status(user=Depends(current_user)) -> RetrievalProfileStatus:
    del user
    return build_profile_status(get_settings().embedding_model)
