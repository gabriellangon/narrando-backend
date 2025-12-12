"""
Translation service for tours, attractions and cities.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

from utils.logging_config import get_logger, verbose_logging_enabled

DEFAULT_LANGUAGES = ["fr", "es", "it", "de", "pt"]
logger = get_logger(__name__)
_verbose_logger = get_logger("translation.transcripts")
VERBOSE_LOGS = verbose_logging_enabled()


class TranslationService:
    def __init__(
        self,
        supabase_client,
        language_client,
        target_languages: Optional[List[str]] = None,
        max_workers: int = 3,
        batch_size: int = 25,
    ):
        self.supabase = supabase_client
        self.language_client = language_client
        self.target_languages = target_languages or DEFAULT_LANGUAGES
        self.max_workers = max_workers
        self.batch_size = batch_size

    # ------------------------------------------------------------------ #
    def translate_city_assets(
        self,
        city_id: str,
        tour_ids: List[str],
    ):
        if not self.supabase or not self.language_client:
            logger.warning("⚠️ Service de traduction indisponible, étape ignorée.")
            return

        city = self._fetch_city(city_id)
        tours = self._fetch_tours(tour_ids)
        attractions = self._fetch_attractions(city_id)

        if not city:
            logger.warning("⚠️ Ville introuvable pour traduction, étape ignorée.")
            return

        languages = [lang for lang in self.target_languages if lang != "en"]
        if not languages:
            logger.warning("⚠️ Aucun code langue cible configuré, étape traduction ignorée.")
            return

        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(languages))) as executor:
            futures = {
                executor.submit(
                    self._translate_for_language,
                    lang,
                    city,
                    tours,
                    attractions,
                ): lang
                for lang in languages
            }

            for future in as_completed(futures):
                lang = futures[future]
                try:
                    future.result()
                    logger.info("✅ Traductions enregistrées pour la langue '%s'", lang)
                except Exception as exc:
                    logger.error("❌ Traduction impossible pour '%s': %s", lang, exc)
                    raise

    # ------------------------------------------------------------------ #
    def _translate_for_language(
        self,
        language_code: str,
        city: Dict[str, str],
        tours: List[Dict[str, str]],
        attractions: List[Dict[str, str]],
    ):
        # City translation
        city_translation = self.language_client.translate_batch(
            [city.get("city", ""), city.get("country", "")],
            target_language=language_code,
            source_language="en",
        )
        self._log_translations(
            label=f"city ({language_code})",
            original=[city.get("city", ""), city.get("country", "")],
            translated=city_translation,
            verbose=VERBOSE_LOGS
        )
        city_payload = [{
            "city_id": city["id"],
            "language_code": language_code,
            "city": city_translation[0] if len(city_translation) > 0 else city.get("city", ""),
            "country": city_translation[1] if len(city_translation) > 1 else city.get("country", "")
        }]
        self._upsert("city_translations", city_payload, "city_id,language_code")

        # Tour names
        if tours:
            tour_names = [t.get("tour_name", "") for t in tours]
            translated_tours = self.language_client.translate_batch(
                tour_names,
                target_language=language_code,
                source_language="en",
            )
            self._log_translations(
                label=f"tours ({language_code})",
                original=tour_names,
                translated=translated_tours,
                verbose=VERBOSE_LOGS
            )
            tour_records = [{
                "tour_id": tour["id"],
                "language_code": language_code,
                "tour_name": translated_tours[idx] if idx < len(translated_tours) else tour_names[idx]
            } for idx, tour in enumerate(tours)]

            self._upsert("guided_tour_translations", tour_records, "tour_id,language_code")

        # Attraction names
        if attractions:
            attraction_names = [a.get("name", "") for a in attractions]
            translated_attractions = self.language_client.translate_batch(
                attraction_names,
                target_language=language_code,
                source_language="en",
            )
            self._log_translations(
                label=f"attractions ({language_code})",
                original=attraction_names,
                translated=translated_attractions,
                verbose=VERBOSE_LOGS
            )

            attraction_records = [{
                "attraction_id": attraction["id"],
                "language_code": language_code,
                "name": translated_attractions[idx] if idx < len(translated_attractions) else attraction_names[idx]
            } for idx, attraction in enumerate(attractions)]

            self._upsert("attraction_translations", attraction_records, "attraction_id,language_code")

    # ------------------------------------------------------------------ #
    def _fetch_city(self, city_id: str) -> Optional[Dict]:
        response = self.supabase.table("cities").select("id, city, country").eq("id", city_id).execute()
        data = response.data or []
        return data[0] if data else None

    def _fetch_tours(self, tour_ids: List[str]) -> List[Dict]:
        if not tour_ids:
            return []
        response = self.supabase.table("guided_tours").select("id, tour_name").in_("id", tour_ids).execute()
        return response.data or []

    def _fetch_attractions(self, city_id: str) -> List[Dict]:
        response = (
            self.supabase.table("attractions")
            .select("id, name")
            .eq("city_id", city_id)
            .order("route_index", desc=False)
            .execute()
        )
        return response.data or []

    def _upsert(self, table: str, records: List[Dict], on_conflict: str):
        for chunk in self._chunk(records, self.batch_size):
            if not chunk:
                continue
            self.supabase.table(table).upsert(chunk, on_conflict=on_conflict).execute()

    @staticmethod
    def _chunk(items: List[Dict], size: int) -> List[List[Dict]]:
        if size <= 0:
            return [items]
        return [items[i:i + size] for i in range(0, len(items), size)]

    @staticmethod
    def _log_translations(label: str, original: List[str], translated: List[str], verbose: bool = False):
        if not verbose:
            return
        _verbose_logger.debug("📝 Traductions %s:", label)
        max_len = max(len(original), len(translated))
        for idx in range(max_len):
            src = original[idx] if idx < len(original) else ""
            tgt = translated[idx] if idx < len(translated) else ""
            _verbose_logger.debug("   [%s] SRC: %s", idx, src)
            _verbose_logger.debug("       TGT: %s", tgt)
