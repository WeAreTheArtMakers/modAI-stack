"""Human-readable retrieval profile metadata; mappings stay evaluation-gated."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


ProfileAvailability = Literal[
    "active",
    "available_after_provisioning",
    "experimental",
    "not_configured",
]


class RetrievalProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    profile_id: str
    display_name: str
    description: str
    language_capabilities: list[str]
    hardware_class: str
    availability: ProfileAvailability
    active: bool = False
    selectable: bool = False


class RetrievalProfileCatalog(BaseModel):
    profiles: list[RetrievalProfile]
    active_profile_id: str | None
    profile_switching_enabled: bool = False


class RetrievalProfileStatus(BaseModel):
    active_profile: RetrievalProfile | None
    profile_switching_enabled: bool = False
    reindex_required_to_change_profile: bool = True


CURRENT_MINILM_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

_PROFILE_CATALOG: tuple[RetrievalProfile, ...] = (
    RetrievalProfile(
        profile_id="compact-multilingual",
        display_name="Compact Multilingual",
        description=(
            "Türkçe, İngilizce ve çok dilli kullanım için düşük bellekli, hızlı yerel kurulum hedefi. "
            "Model eşlemesi ve kalite ölçümü henüz doğrulanmadı."
        ),
        language_capabilities=["Türkçe + English + multilingual hedefi; ölçüm bekliyor"],
        hardware_class="Düşük kaynak / hızlı",
        availability="experimental",
    ),
    RetrievalProfile(
        profile_id="balanced-multilingual",
        display_name="Balanced Multilingual",
        description=(
            "Çok dilli retrieval kalitesi ile yerel kaynak kullanımını dengelemek için tasarlanır. "
            "Model eşlemesi benchmark sonrasında yapılacak."
        ),
        language_capabilities=["Çok dilli hedef; ölçüm bekliyor"],
        hardware_class="Orta kaynak",
        availability="available_after_provisioning",
    ),
    RetrievalProfile(
        profile_id="advanced-long-document",
        display_name="Advanced Long-Document",
        description=(
            "Uzun belgeler ve çok dilli koleksiyonlar için yüksek kaynak sınıfı hedefi. "
            "Üretim modeli ve indeks davranışı henüz seçilmedi."
        ),
        language_capabilities=["Çok dilli hedef; ölçüm bekliyor"],
        hardware_class="Yüksek kaynak",
        availability="not_configured",
    ),
    RetrievalProfile(
        profile_id="english-optimized",
        display_name="English Optimized",
        description=(
            "Hafif, İngilizce odaklı mevcut embedding baseline'ı. "
            "Türkçe optimizasyonu veya üstün retrieval kalitesi iddia edilmez."
        ),
        language_capabilities=["English-focused", "Türkçe performansı benchmark edilmedi"],
        hardware_class="Düşük kaynak",
        availability="not_configured",
    ),
)


def determine_active_profile_id(embedding_model: str) -> str | None:
    """Map only the verified current model; unknown identifiers stay unmapped."""
    if embedding_model == CURRENT_MINILM_MODEL:
        return "english-optimized"
    return None


def build_profile_catalog(embedding_model: str) -> RetrievalProfileCatalog:
    active_profile_id = determine_active_profile_id(embedding_model)
    profiles = [
        profile.model_copy(
            update={
                "active": profile.profile_id == active_profile_id,
                "availability": "active" if profile.profile_id == active_profile_id else profile.availability,
            }
        )
        for profile in _PROFILE_CATALOG
    ]
    return RetrievalProfileCatalog(profiles=profiles, active_profile_id=active_profile_id)


def build_profile_status(embedding_model: str) -> RetrievalProfileStatus:
    catalog = build_profile_catalog(embedding_model)
    active_profile = next((item for item in catalog.profiles if item.active), None)
    return RetrievalProfileStatus(active_profile=active_profile)
