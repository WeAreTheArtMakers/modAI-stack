from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import AssistantPreference
from app.models.schemas import AssistantPreferencesUpdate


DEFAULT_ASSISTANT_PREFERENCES = {
    "assistant_name": "modAI",
    "language": "auto",
    "tone": "professional",
    "response_length": "balanced",
}


def generation_preference_values(preferences: AssistantPreference | dict) -> dict[str, str]:
    return {
        "language": preferences["language"] if isinstance(preferences, dict) else preferences.language,
        "tone": preferences["tone"] if isinstance(preferences, dict) else preferences.tone,
        "response_length": preferences["response_length"] if isinstance(preferences, dict) else preferences.response_length,
    }


async def get_effective_assistant_preferences(
    db: AsyncSession,
    user_id: int,
) -> AssistantPreference | dict:
    preference = await db.scalar(
        select(AssistantPreference).where(
            AssistantPreference.user_id == user_id
        )
    )
    return preference if preference is not None else DEFAULT_ASSISTANT_PREFERENCES


async def upsert_assistant_preferences(
    db: AsyncSession,
    user_id: int,
    preferences: AssistantPreferencesUpdate,
) -> AssistantPreference:
    values = preferences.model_dump()
    values["user_id"] = user_id
    dialect = db.get_bind().dialect.name

    if dialect == "postgresql":
        statement = pg_insert(AssistantPreference).values(**values)
        statement = statement.on_conflict_do_update(
            index_elements=[AssistantPreference.user_id],
            set_={**preferences.model_dump(), "updated_at": func.now()},
        )
        await db.execute(statement)
    elif dialect == "sqlite":
        statement = sqlite_insert(AssistantPreference).values(**values)
        statement = statement.on_conflict_do_update(
            index_elements=[AssistantPreference.user_id],
            set_={**preferences.model_dump(), "updated_at": func.now()},
        )
        await db.execute(statement)
    else:
        existing = await db.scalar(
            select(AssistantPreference).where(
                AssistantPreference.user_id == user_id
            )
        )
        if existing is None:
            db.add(AssistantPreference(**values))
        else:
            for key, value in preferences.model_dump().items():
                setattr(existing, key, value)

    await db.commit()
    preference = await db.scalar(
        select(AssistantPreference).where(
            AssistantPreference.user_id == user_id
        )
    )
    assert preference is not None
    return preference
