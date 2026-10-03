from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.deps import current_user
from app.api.routes import retrieval as retrieval_routes
from app.main import app
from app.services.rag.retrieval_profiles import (
    build_profile_catalog,
    build_profile_status,
    determine_active_profile_id,
)


CURRENT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def test_profile_catalog_serializes_human_facing_catalog_without_model_identity():
    catalog = build_profile_catalog(CURRENT_MODEL).model_dump(mode="json")

    assert catalog["active_profile_id"] == "english-optimized"
    assert catalog["profile_switching_enabled"] is False
    assert [profile["profile_id"] for profile in catalog["profiles"]] == [
        "compact-multilingual",
        "balanced-multilingual",
        "advanced-long-document",
        "english-optimized",
    ]
    active = next(profile for profile in catalog["profiles"] if profile["active"])
    assert active["display_name"] == "English Optimized"
    assert active["availability"] == "active"
    assert active["selectable"] is False
    assert "Türkçe performansı benchmark edilmedi" in active["language_capabilities"]
    assert "embedding_model" not in str(catalog)
    assert "cache_dir" not in str(catalog)
    assert "model_path" not in str(catalog)


def test_profile_catalog_inactive_statuses_are_explicit_and_not_selectable():
    catalog = build_profile_catalog(CURRENT_MODEL)
    profiles = {profile.profile_id: profile for profile in catalog.profiles}

    assert profiles["compact-multilingual"].availability == "experimental"
    assert profiles["balanced-multilingual"].availability == "available_after_provisioning"
    assert profiles["advanced-long-document"].availability == "not_configured"
    assert all(not profile.selectable for profile in catalog.profiles)


def test_unknown_embedding_configuration_does_not_guess_or_expose_profile():
    unknown_model_path = "/private/local/cache/company-model"

    assert determine_active_profile_id(unknown_model_path) is None
    catalog = build_profile_catalog(unknown_model_path)
    status = build_profile_status(unknown_model_path)

    assert catalog.active_profile_id is None
    assert all(not profile.active for profile in catalog.profiles)
    assert status.active_profile is None
    assert unknown_model_path not in catalog.model_dump_json()
    assert unknown_model_path not in status.model_dump_json()


def test_read_only_profile_endpoints_preserve_embedding_setting_and_hide_paths(monkeypatch, tmp_path):
    model_path = tmp_path / "private-embedding-cache"
    settings = SimpleNamespace(embedding_model=str(model_path))
    monkeypatch.setattr(retrieval_routes, "get_settings", lambda: settings)
    app.dependency_overrides[current_user] = lambda: {"sub": "9", "role": "user"}
    try:
        client = TestClient(app)
        profiles_response = client.get("/retrieval/profiles")
        status_response = client.get("/retrieval/status")
        write_response = client.post("/retrieval/profiles", json={"profile_id": "compact-multilingual"})
    finally:
        app.dependency_overrides.pop(current_user, None)

    assert profiles_response.status_code == 200
    assert status_response.status_code == 200
    assert write_response.status_code == 405
    assert settings.embedding_model == str(model_path)
    assert str(model_path) not in profiles_response.text
    assert str(model_path) not in status_response.text
    assert "embedding_model" not in profiles_response.text
    assert "embedding_model" not in status_response.text
    assert profiles_response.json()["active_profile_id"] is None
    assert status_response.json() == {
        "active_profile": None,
        "profile_switching_enabled": False,
        "reindex_required_to_change_profile": True,
    }


def test_known_current_model_maps_only_to_english_lightweight_profile():
    status = build_profile_status(CURRENT_MODEL)

    assert status.active_profile is not None
    assert status.active_profile.profile_id == "english-optimized"
    assert status.active_profile.language_capabilities == [
        "English-focused",
        "Türkçe performansı benchmark edilmedi",
    ]
    assert status.profile_switching_enabled is False
    assert status.reindex_required_to_change_profile is True
