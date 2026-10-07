from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user
from app.db.session import get_db
from app.models.database import AssistantPreference
from app.models.schemas import (
    AssistantPreferencesResponse,
    AssistantPreferencesUpdate,
)
from app.services.assistant_preferences import (
    get_effective_assistant_preferences,
    upsert_assistant_preferences,
)


router = APIRouter(prefix="/assistant/preferences", tags=["assistant"])


def _response_values(
    preferences: AssistantPreference | dict[str, str],
) -> AssistantPreferencesResponse:
    if isinstance(preferences, dict):
        return AssistantPreferencesResponse(**preferences)
    return AssistantPreferencesResponse(
        assistant_name=preferences.assistant_name,
        language=preferences.language,
        tone=preferences.tone,
        response_length=preferences.response_length,
        updated_at=preferences.updated_at,
    )


@router.get("", response_model=AssistantPreferencesResponse)
async def get_preferences(
    user=Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    preferences = await get_effective_assistant_preferences(
        db, int(user["sub"])
    )
    return _response_values(preferences)


@router.put("", response_model=AssistantPreferencesResponse)
async def update_preferences(
    req: AssistantPreferencesUpdate,
    user=Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    preferences = await upsert_assistant_preferences(
        db,
        int(user["sub"]),
        req,
    )
    return _response_values(preferences)
