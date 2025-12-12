from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


class TableMock:
    def __init__(self, name, operations):
        self.name = name
        self.operations = operations

    def update(self, payload):
        self.operations.append(
            {"table": self.name, "op": "update", "payload": payload}
        )
        return self

    def delete(self):
        self.operations.append({"table": self.name, "op": "delete"})
        return self

    def select(self, *args, **kwargs):
        self.operations.append({"table": self.name, "op": "select"})
        return self

    def eq(self, column, value):
        self.operations.append(
            {"table": self.name, "op": "eq", "column": column, "value": value}
        )
        return self

    def neq(self, column, value):
        self.operations.append(
            {"table": self.name, "op": "neq", "column": column, "value": value}
        )
        return self

    def execute(self):
        return SimpleNamespace(data=[])


class MockSupabase:
    def __init__(self):
        self.operations = []

    def table(self, name):
        return TableMock(name, self.operations)


class DummyMigrator:
    def __init__(self, supabase, migration_result=None, tour_data=None):
        self.supabase = supabase
        self.migration_result = migration_result or {
            "success": True,
            "city_id": "city-123",
            "tour_ids": ["tour-1"],
            "tours_count": 1,
            "attractions_count": 2,
        }
        self.tour_data = tour_data
        self.description_updates = []
        self.audio_updates = []
        self.walking_paths = []
        self.migration_call = None

    def migrate_route_data_with_source_attractions(
        self, optimized_route, filtered_attractions
    ):
        self.migration_call = (optimized_route, filtered_attractions)
        return self.migration_result

    def get_specific_tour_by_id(self, tour_id):
        return self.tour_data

    def update_attraction_description(
        self, place_id, description, narration_type, language_code
    ):
        self.description_updates.append(
            {
                "place_id": place_id,
                "description": description,
                "narration_type": narration_type,
                "language_code": language_code,
            }
        )

    def update_attraction_audio_url(
        self, place_id, audio_url, narration_type, language_code
    ):
        self.audio_updates.append(
            {
                "place_id": place_id,
                "audio_url": audio_url,
                "narration_type": narration_type,
                "language_code": language_code,
            }
        )

    def ensure_walking_paths_for_tour(self, tour_id, attractions, generator):
        self.walking_paths.append({"tour_id": tour_id, "attractions": attractions})


class TranslationServiceSpy:
    def __init__(self):
        self.calls = []

    def translate_city_assets(self, city_id, tour_ids):
        self.calls.append((city_id, tour_ids))


def test_generate_tour_from_place_id_runs_pipeline(api_module):
    supabase = MockSupabase()
    migrator = DummyMigrator(
        supabase,
        migration_result={
            "success": True,
            "city_id": "city-123",
            "tour_ids": ["tour-1"],
            "tours_count": 1,
            "attractions_count": 2,
        },
    )
    translation_service = TranslationServiceSpy()

    api = api_module.NarrandoAPI.__new__(api_module.NarrandoAPI)
    api.migrator = migrator
    api.translation_service = translation_service
    api.language_client = None
    api.translation_languages = ["fr"]
    api.tts_client = SimpleNamespace(client=True)
    api._assign_tour_names = lambda optimized_route: optimized_route
    api._mirror_photos_to_s3 = lambda attractions, max_photos, workers: attractions
    api.get_city_from_place_id = lambda place_id: {
        "place_id": place_id,
        "city": "Paris",
        "country": "France",
        "country_iso": "FR",
        "formatted_address": "Paris, France",
        "location": {"lat": 1.0, "lng": 2.0},
    }
    attractions = [
        {"name": "Orsay", "place_id": "p1", "types": [], "photos": []},
        {"name": "Louvre", "place_id": "p2", "types": [], "photos": []},
        {"name": "Invalides", "place_id": "p3", "types": [], "photos": []},
    ]
    api.google_client = SimpleNamespace(
        search_tourist_attractions=lambda city, country, max_results=30: attractions
    )
    api.perplexity_client = SimpleNamespace(
        filter_attractions=lambda attractions, city, country: attractions[:2]
    )
    api.route_optimizer = SimpleNamespace(
        optimize_route=lambda attrs: {"tours": [{"points": attrs}]}
    )

    result = api.generate_tour_from_place_id("test-place-id")

    assert result["city"] == "Paris"
    assert result["country"] == "France"
    assert result["tour_ids"] == ["tour-1"]
    assert result["migration_success"] is True
    assert result["tours_count"] == 1
    assert translation_service.calls == [("city-123", ["tour-1"])]

    updates = [
        op for op in supabase.operations if op["op"] == "update" and op["table"] == "processing_city"
    ]
    assert updates[-1]["payload"]["progress_percent"] == 100
    assert updates[-1]["payload"]["status"] == "completed"


def test_generate_tour_from_place_id_marks_error(api_module):
    supabase = MockSupabase()
    migrator = DummyMigrator(supabase)

    api = api_module.NarrandoAPI.__new__(api_module.NarrandoAPI)
    api.migrator = migrator
    api.translation_service = None
    api.language_client = None
    api.translation_languages = []
    api.tts_client = SimpleNamespace(client=True)
    api._assign_tour_names = lambda optimized_route: optimized_route
    api._mirror_photos_to_s3 = lambda attractions, max_photos, workers: attractions
    api.get_city_from_place_id = lambda place_id: (_ for _ in ()).throw(Exception("boom"))
    api.google_client = SimpleNamespace(
        search_tourist_attractions=lambda city, country, max_results=30: []
    )
    api.perplexity_client = SimpleNamespace(
        filter_attractions=lambda attractions, city, country: []
    )
    api.route_optimizer = SimpleNamespace(optimize_route=lambda attrs: {})

    with pytest.raises(Exception) as exc:
        api.generate_tour_from_place_id("bad-place")

    assert "Erreur génération tour" in str(exc.value)
    error_updates = [
        op
        for op in supabase.operations
        if op["op"] == "update"
        and op["table"] == "processing_city"
        and op["payload"].get("status") == "error"
    ]
    assert error_updates
    assert error_updates[-1]["payload"]["progress_percent"] == 100
    assert error_updates[-1]["payload"]["current_step_key"] == "error"


def test_generate_preview_audio_reuses_existing_audio(api_module):
    supabase = MockSupabase()
    tour_data = {
        "tour": {
            "id": "tour-1",
            "name": "Tour name",
            "attractions": [
                {
                    "name": "Arc de Triomphe",
                    "place_id": "p1",
                    "audio_url": {"standard": "https://audio.existing"},
                    "ai_description": {"standard": "Existing description"},
                    "point_order": 1,
                }
            ],
        },
        "city": {"id": "city-1"},
    }
    migrator = DummyMigrator(supabase, tour_data=tour_data)

    api = api_module.NarrandoAPI.__new__(api_module.NarrandoAPI)
    api.migrator = migrator
    api.translation_service = None
    api.language_client = None
    api.route_optimizer = SimpleNamespace(generate_walking_path=lambda *args, **kwargs: None)
    api.translation_languages = []
    api.tts_client = SimpleNamespace(client=True)
    api._ensure_walking_paths_ready = MagicMock()
    api._get_translation_assets = lambda place_id, language_code: {}
    api.generate_attraction_description = MagicMock()
    api.generate_audio_from_description = MagicMock()

    preview = api.generate_preview_audio(
        "tour-1",
        attraction_index=0,
        force_regenerate=False,
        narration_type="standard",
        language_code="en",
    )

    assert preview["audio_url"] == "https://audio.existing"
    api.generate_attraction_description.assert_not_called()
    api.generate_audio_from_description.assert_not_called()
    api._ensure_walking_paths_ready.assert_called_once()


def test_generate_preview_audio_generates_missing_assets(api_module):
    supabase = MockSupabase()
    tour_data = {
        "tour": {
            "id": "tour-1",
            "name": "Tour name",
            "attractions": [
                {
                    "name": "Pantheon",
                    "place_id": "p1",
                    "point_order": 2,
                }
            ],
        },
        "city": {"id": "city-1"},
    }
    migrator = DummyMigrator(supabase, tour_data=tour_data)

    api = api_module.NarrandoAPI.__new__(api_module.NarrandoAPI)
    api.migrator = migrator
    api.translation_service = None
    api.language_client = None
    api.route_optimizer = SimpleNamespace(generate_walking_path=lambda *args, **kwargs: None)
    api.translation_languages = []
    api.tts_client = SimpleNamespace(client=True)
    api._ensure_walking_paths_ready = MagicMock()
    api._get_translation_assets = lambda place_id, language_code: {}
    api.generate_attraction_description = MagicMock(return_value="Generated description")
    api.generate_audio_from_description = MagicMock(return_value="https://audio/new.mp3")

    preview = api.generate_preview_audio(
        "tour-1",
        attraction_index=0,
        force_regenerate=False,
        narration_type="standard",
        language_code="en",
    )

    assert preview["audio_url"] == "https://audio/new.mp3"
    assert preview["description"] == "Generated description"
    assert migrator.description_updates[0]["place_id"] == "p1"
    assert migrator.audio_updates[0]["audio_url"] == "https://audio/new.mp3"
    api.generate_attraction_description.assert_called_once()
    api.generate_audio_from_description.assert_called_once()
    api._ensure_walking_paths_ready.assert_called_once()


def test_generate_audio_from_description_uploads_to_s3(api_module, dummy_s3, monkeypatch):
    api = api_module.NarrandoAPI.__new__(api_module.NarrandoAPI)
    voice_id_mock = MagicMock(return_value="voice-id")
    generate_audio_mock = MagicMock(return_value=b"audio-bytes")
    api.tts_client = SimpleNamespace(
        client=True,
        get_voice_id=voice_id_mock,
        generate_tourist_guide_audio=generate_audio_mock,
    )

    api_module.s3_client = dummy_s3
    api_module.S3_BUCKET = "test-bucket"
    monkeypatch.setenv("DEV_MODE", "false")
    monkeypatch.setattr(api_module.time, "time", lambda: 1700000000)

    url = api.generate_audio_from_description(
        "Some description",
        "filename",
        "city-99",
        "tour-42",
        content_type="attraction",
        narration_type="standard",
        language_code="en",
    )

    expected_key = "audio/city-99/tour-42/filename_1700000000.mp3"
    assert url == f"https://test-bucket.s3.amazonaws.com/{expected_key}"
    assert dummy_s3.put_calls[-1]["Key"] == expected_key
    generate_audio_mock.assert_called_once()
    voice_id_mock.assert_called_once_with("en")


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================


def test_generate_complete_tour_audio_tour_not_found(api_module):
    """Test error when tour_id does not exist"""
    supabase = MockSupabase()
    migrator = DummyMigrator(supabase, tour_data=None)

    api = api_module.NarrandoAPI.__new__(api_module.NarrandoAPI)
    api.migrator = migrator

    with pytest.raises(Exception) as exc:
        api.generate_complete_tour_audio("nonexistent-tour-id")

    assert "Tour avec ID nonexistent-tour-id non trouvé" in str(exc.value)


def test_generate_complete_tour_audio_no_attractions(api_module):
    """Test error when tour has no attractions"""
    supabase = MockSupabase()
    tour_data = {
        "tour": {
            "id": "tour-1",
            "name": "Empty Tour",
            "attractions": [],
        },
        "city": {"id": "city-1"},
    }
    migrator = DummyMigrator(supabase, tour_data=tour_data)

    api = api_module.NarrandoAPI.__new__(api_module.NarrandoAPI)
    api.migrator = migrator

    with pytest.raises(Exception) as exc:
        api.generate_complete_tour_audio("tour-1")

    assert "aucune attraction" in str(exc.value)


def test_generate_complete_tour_audio_description_generation_fails(api_module):
    """Test error when generate_attraction_description returns None"""
    supabase = MockSupabase()
    tour_data = {
        "tour": {
            "id": "tour-1",
            "name": "Test Tour",
            "attractions": [
                {
                    "name": "Failing Attraction",
                    "place_id": "p1",
                    "point_order": 1,
                    "id": "attr-1",
                }
            ],
        },
        "city": {"id": "city-1"},
    }
    migrator = DummyMigrator(supabase, tour_data=tour_data)

    api = api_module.NarrandoAPI.__new__(api_module.NarrandoAPI)
    api.migrator = migrator
    api.route_optimizer = SimpleNamespace(generate_walking_path=lambda *args, **kwargs: None)
    api._ensure_walking_paths_ready = MagicMock()
    api._get_translation_assets = lambda place_id, language_code: {}
    # Simulate description generation failure
    api.generate_attraction_description = MagicMock(return_value=None)

    with pytest.raises(Exception) as exc:
        api.generate_complete_tour_audio("tour-1")

    assert "Description non générée pour Failing Attraction" in str(exc.value)


# =============================================================================
# MULTI-LANGUAGE TESTS
# =============================================================================


def test_generate_complete_tour_audio_french_uses_translation_assets(api_module):
    """Test that non-English languages fetch from translation_assets"""
    supabase = MockSupabase()
    tour_data = {
        "tour": {
            "id": "tour-1",
            "name": "Paris Tour",
            "attractions": [
                {
                    "name": "Eiffel Tower",
                    "place_id": "p1",
                    "point_order": 1,
                    "id": "attr-1",
                }
            ],
        },
        "city": {"id": "city-1"},
    }
    migrator = DummyMigrator(supabase, tour_data=tour_data)

    api = api_module.NarrandoAPI.__new__(api_module.NarrandoAPI)
    api.migrator = migrator
    api.route_optimizer = SimpleNamespace(generate_walking_path=lambda *args, **kwargs: None)
    api._ensure_walking_paths_ready = MagicMock()

    # Mock _get_translation_assets to return French translation
    translation_assets_calls = []

    def mock_get_translation_assets(place_id, language_code):
        translation_assets_calls.append((place_id, language_code))
        return {
            "ai_description": {"standard": "Description en français"},
            "audio_url": {"standard": "https://existing-french-audio.mp3"},
        }

    api._get_translation_assets = mock_get_translation_assets
    api.generate_attraction_description = MagicMock(return_value="Generated French")
    api.generate_audio_from_description = MagicMock(return_value="https://new-audio.mp3")

    result = api.generate_complete_tour_audio(
        "tour-1",
        narration_type="standard",
        language_code="fr",
    )

    # Should have called _get_translation_assets with French
    assert ("p1", "fr") in translation_assets_calls
    # Audio already exists in translation_assets, so no generation needed
    assert result["total_generated"] == 0
    assert result["language_code"] == "fr"


def test_generate_complete_tour_audio_french_generates_missing(api_module):
    """Test that French audio is generated when not in translation_assets"""
    supabase = MockSupabase()
    tour_data = {
        "tour": {
            "id": "tour-1",
            "name": "Paris Tour",
            "attractions": [
                {
                    "name": "Louvre",
                    "place_id": "p2",
                    "point_order": 1,
                    "id": "attr-2",
                }
            ],
        },
        "city": {"id": "city-1"},
    }
    migrator = DummyMigrator(supabase, tour_data=tour_data)

    api = api_module.NarrandoAPI.__new__(api_module.NarrandoAPI)
    api.migrator = migrator
    api.route_optimizer = SimpleNamespace(generate_walking_path=lambda *args, **kwargs: None)
    api._ensure_walking_paths_ready = MagicMock()

    # No existing French translation
    api._get_translation_assets = lambda place_id, language_code: {}
    api.generate_attraction_description = MagicMock(return_value="Description Louvre en français")
    api.generate_audio_from_description = MagicMock(return_value="https://new-french-audio.mp3")

    result = api.generate_complete_tour_audio(
        "tour-1",
        narration_type="standard",
        language_code="fr",
    )

    # Should have generated new audio
    assert result["total_generated"] == 1
    assert result["language_code"] == "fr"
    api.generate_attraction_description.assert_called_once()
    api.generate_audio_from_description.assert_called_once()
    # Verify description was saved via migrator
    assert len(migrator.description_updates) == 1
    assert migrator.description_updates[0]["language_code"] == "fr"


# =============================================================================
# GENERATE COMPLETE TOUR AUDIO TESTS
# =============================================================================


def test_generate_complete_tour_audio_processes_all_attractions(api_module):
    """Test that all attractions are processed in order"""
    supabase = MockSupabase()
    tour_data = {
        "tour": {
            "id": "tour-1",
            "name": "Complete Tour",
            "attractions": [
                {"name": "Point A", "place_id": "p1", "point_order": 1, "id": "a1"},
                {"name": "Point B", "place_id": "p2", "point_order": 2, "id": "a2"},
                {"name": "Point C", "place_id": "p3", "point_order": 3, "id": "a3"},
            ],
        },
        "city": {"id": "city-1"},
    }
    migrator = DummyMigrator(supabase, tour_data=tour_data)

    api = api_module.NarrandoAPI.__new__(api_module.NarrandoAPI)
    api.migrator = migrator
    api.route_optimizer = SimpleNamespace(generate_walking_path=lambda *args, **kwargs: None)
    api._ensure_walking_paths_ready = MagicMock()
    api._get_translation_assets = lambda place_id, language_code: {}
    api.generate_attraction_description = MagicMock(side_effect=lambda a, nt, lc: f"Desc for {a['name']}")
    api.generate_audio_from_description = MagicMock(side_effect=lambda d, f, c, t, ct, nt, lc: f"https://audio/{f}.mp3")

    result = api.generate_complete_tour_audio("tour-1")

    assert result["total_generated"] == 3
    assert result["total_attractions"] == 3
    assert len(result["generated_audios"]) == 3

    # Verify order
    assert result["generated_audios"][0]["attraction_name"] == "Point A"
    assert result["generated_audios"][1]["attraction_name"] == "Point B"
    assert result["generated_audios"][2]["attraction_name"] == "Point C"

    # Verify descriptions and audio URLs saved
    assert len(migrator.description_updates) == 3
    assert len(migrator.audio_updates) == 3


def test_generate_complete_tour_audio_skips_existing(api_module):
    """Test that existing audio is skipped when force_regenerate=False"""
    supabase = MockSupabase()
    tour_data = {
        "tour": {
            "id": "tour-1",
            "name": "Mixed Tour",
            "attractions": [
                {
                    "name": "Existing",
                    "place_id": "p1",
                    "point_order": 1,
                    "id": "a1",
                    "audio_url": {"standard": "https://existing.mp3"},
                    "ai_description": {"standard": "Existing description"},
                },
                {"name": "New", "place_id": "p2", "point_order": 2, "id": "a2"},
            ],
        },
        "city": {"id": "city-1"},
    }
    migrator = DummyMigrator(supabase, tour_data=tour_data)

    api = api_module.NarrandoAPI.__new__(api_module.NarrandoAPI)
    api.migrator = migrator
    api.route_optimizer = SimpleNamespace(generate_walking_path=lambda *args, **kwargs: None)
    api._ensure_walking_paths_ready = MagicMock()
    api._get_translation_assets = lambda place_id, language_code: {}
    api.generate_attraction_description = MagicMock(return_value="New description")
    api.generate_audio_from_description = MagicMock(return_value="https://new-audio.mp3")

    result = api.generate_complete_tour_audio("tour-1", force_regenerate=False)

    # Only one new attraction generated
    assert result["total_generated"] == 1
    assert result["generated_audios"][0]["attraction_name"] == "New"


# =============================================================================
# WALKING PATHS TESTS
# =============================================================================


def test_ensure_walking_paths_ready_calls_migrator(api_module):
    """Test that _ensure_walking_paths_ready delegates to migrator"""
    supabase = MockSupabase()
    tour_data = {
        "tour": {
            "id": "tour-1",
            "name": "Walking Tour",
            "attractions": [
                {"name": "Start", "place_id": "p1", "point_order": 1},
                {"name": "End", "place_id": "p2", "point_order": 2},
            ],
        },
        "city": {"id": "city-1"},
    }
    migrator = DummyMigrator(supabase, tour_data=tour_data)

    api = api_module.NarrandoAPI.__new__(api_module.NarrandoAPI)
    api.migrator = migrator
    api.route_optimizer = SimpleNamespace(generate_walking_path=lambda *args, **kwargs: {"path": "mock"})

    attractions = tour_data["tour"]["attractions"]
    api._ensure_walking_paths_ready("tour-1", attractions)

    # Verify migrator.ensure_walking_paths_for_tour was called
    assert len(migrator.walking_paths) == 1
    assert migrator.walking_paths[0]["tour_id"] == "tour-1"
    assert migrator.walking_paths[0]["attractions"] == attractions


def test_generate_complete_tour_audio_ensures_walking_paths(api_module):
    """Test that generate_complete_tour_audio calls _ensure_walking_paths_ready"""
    supabase = MockSupabase()
    tour_data = {
        "tour": {
            "id": "tour-1",
            "name": "Walking Tour",
            "attractions": [
                {
                    "name": "Only Point",
                    "place_id": "p1",
                    "point_order": 1,
                    "id": "a1",
                    "audio_url": {"standard": "https://existing.mp3"},
                }
            ],
        },
        "city": {"id": "city-1"},
    }
    migrator = DummyMigrator(supabase, tour_data=tour_data)

    api = api_module.NarrandoAPI.__new__(api_module.NarrandoAPI)
    api.migrator = migrator
    api.route_optimizer = SimpleNamespace(generate_walking_path=lambda *args, **kwargs: None)
    api._get_translation_assets = lambda place_id, language_code: {}

    ensure_mock = MagicMock()
    api._ensure_walking_paths_ready = ensure_mock

    api.generate_complete_tour_audio("tour-1")

    ensure_mock.assert_called_once()
    call_args = ensure_mock.call_args[0]
    assert call_args[0] == "tour-1"


def test_ensure_walking_paths_ready_fails_without_supabase(api_module):
    """Test that _ensure_walking_paths_ready raises when Supabase unavailable"""
    api = api_module.NarrandoAPI.__new__(api_module.NarrandoAPI)
    api.migrator = None
    api.route_optimizer = SimpleNamespace(generate_walking_path=lambda *args, **kwargs: None)

    with pytest.raises(ValueError) as exc:
        api._ensure_walking_paths_ready("tour-1", [])

    assert "Supabase indisponible" in str(exc.value)


def test_ensure_walking_paths_ready_fails_without_route_optimizer(api_module):
    """Test that _ensure_walking_paths_ready raises when RouteOptimizer unavailable"""
    supabase = MockSupabase()
    migrator = DummyMigrator(supabase)

    api = api_module.NarrandoAPI.__new__(api_module.NarrandoAPI)
    api.migrator = migrator
    api.route_optimizer = None

    with pytest.raises(ValueError) as exc:
        api._ensure_walking_paths_ready("tour-1", [])

    assert "RouteOptimizer non initialisé" in str(exc.value)
