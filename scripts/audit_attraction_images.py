"""
Audit and repair for attraction images stored in Supabase.

Usage:
    python scripts/audit_attraction_images.py [--city-id <uuid>] [--limit N] [--apply]

The script runs in dry-run by default and makes no changes.
Requires SUPABASE_URL, SUPABASE_SERVICE_KEY and GOOGLE_PLACES_API_KEY in the environment.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import requests

# Allow running the script directly from the repo root without editable install
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if REPO_ROOT not in sys.path:
    sys.path.append(REPO_ROOT)

from database.migrate_to_supabase import SupabaseMigrator  # noqa: E402
from utils.logging_config import get_logger  # noqa: E402
from utils.photo_url_generator import GooglePhotoURLGenerator  # noqa: E402

logger = get_logger(__name__)

PAGE_SIZE = 200
PROBE_TIMEOUT = 8
MAX_DEFAULT_NEW_PHOTOS = 3


class AttractionImageAuditor:
    def __init__(self, supabase_client, photo_generator: GooglePhotoURLGenerator):
        self.supabase = supabase_client
        self.photo_generator = photo_generator
        self.google_api_key = photo_generator.google_api_key
        self.session = requests.Session()
        self.place_details_url = "https://maps.googleapis.com/maps/api/place/details/json"

    def audit(
        self,
        city_id: Optional[str] = None,
        limit: Optional[int] = None,
        apply_changes: bool = False,
        max_new_photos: int = MAX_DEFAULT_NEW_PHOTOS,
    ) -> Dict[str, int]:
        counters = {
            "total": 0,
            "with_photos": 0,
            "ok": 0,
            "missing_photos": 0,
            "broken": 0,
            "updated": 0,
            "missing_place_id": 0,
        }

        processed = 0
        for attraction in self._fetch_attractions(city_id=city_id, limit=limit):
            processed += 1
            counters["total"] += 1

            result = self._process_attraction(
                attraction, apply_changes=apply_changes, max_new_photos=max_new_photos
            )

            if result["has_photos"]:
                counters["with_photos"] += 1
            else:
                counters["missing_photos"] += 1

            if result["status"] == "ok":
                counters["ok"] += 1
            elif result["status"] == "broken":
                counters["broken"] += 1
            elif result["status"] == "missing_place_id":
                counters["missing_place_id"] += 1

            if result["updated"]:
                counters["updated"] += 1

            if limit and processed >= limit:
                break

        return counters

    def _fetch_attractions(
        self, city_id: Optional[str], limit: Optional[int]
    ) -> Iterable[Dict]:
        start = 0
        fetched = 0

        while True:
            query = self.supabase.table("attractions").select(
                "id, name, place_id, photos"
            )
            if city_id:
                query = query.eq("city_id", city_id)

            result = query.range(start, start + PAGE_SIZE - 1).execute()
            batch = result.data or []
            if not batch:
                break

            for row in batch:
                yield row
                fetched += 1
                if limit and fetched >= limit:
                    return

            if len(batch) < PAGE_SIZE:
                break
            start += PAGE_SIZE

    def _process_attraction(
        self, attraction: Dict, apply_changes: bool, max_new_photos: int
    ) -> Dict[str, Optional[bool]]:
        attraction_id = attraction.get("id")
        place_id = attraction.get("place_id")
        name = attraction.get("name") or "Unknown"

        photos = self._normalize_photos(attraction.get("photos"))
        valid_photos: List[Dict] = []
        broken_photos: List[Tuple[Dict, str]] = []

        for photo in photos:
            url = self._resolve_photo_url(photo)
            if not url:
                broken_photos.append((photo, "missing_url"))
                continue

            ok, status = self._probe_url(url)
            if ok:
                if photo.get("photo_url") != url:
                    updated_photo = dict(photo)
                    updated_photo["photo_url"] = url
                else:
                    updated_photo = photo
                valid_photos.append(updated_photo)
            else:
                reason = f"http_{status}" if status is not None else "request_failed"
                broken_photos.append((photo, reason))

        status = "ok" if not broken_photos and photos else "broken"
        has_photos = bool(photos)

        if not photos or broken_photos:
            if not place_id:
                logger.warning(
                    "Skipping: attraction without place_id, cannot fetch a photo: %s",
                    name,
                )
                return {
                    "status": "missing_place_id",
                    "has_photos": has_photos,
                    "updated": False,
                }

            new_photos = self._fetch_google_photos(place_id, max_results=max_new_photos)
            if not new_photos:
                logger.warning(
                    "No new photo retrieved for %s (%s)",
                    name,
                    place_id,
                )
            final_photos = self._merge_photos(valid_photos, new_photos, target=len(photos) or max_new_photos or 1)
        else:
            final_photos = valid_photos

        updated = False
        if apply_changes and final_photos != photos:
            self._update_supabase_photos(attraction_id, final_photos)
            updated = True
            logger.info(
                "Photos updated for %s (%s) - old: %s, new: %s",
                name,
                attraction_id,
                len(photos),
                len(final_photos),
            )
        elif not apply_changes and final_photos != photos:
            logger.info(
                "DRY-RUN: %s broken photos for %s (%s) - proposed replacement: %s -> %s",
                len(broken_photos),
                name,
                attraction_id,
                len(photos),
                len(final_photos),
            )

        return {"status": status, "has_photos": has_photos, "updated": updated}

    def _merge_photos(
        self, valid_photos: List[Dict], new_photos: List[Dict], target: int
    ) -> List[Dict]:
        merged = list(valid_photos)
        existing_refs = {
            photo.get("photo_reference") for photo in valid_photos if photo.get("photo_reference")
        }

        for photo in new_photos:
            ref = photo.get("photo_reference")
            if ref and ref in existing_refs:
                continue
            merged.append(photo)
            if ref:
                existing_refs.add(ref)
            if len(merged) >= target:
                break

        return merged

    def _normalize_photos(self, photos: Optional[object]) -> List[Dict]:
        if not photos or not isinstance(photos, list):
            return []
        normalized = []
        for item in photos:
            if isinstance(item, dict):
                normalized.append(item)
        return normalized

    def _resolve_photo_url(self, photo: Dict) -> Optional[str]:
        url = photo.get("photo_url") or photo.get("url")
        if url:
            return url
        ref = photo.get("photo_reference")
        if ref:
            try:
                return self.photo_generator.generate_photo_url(ref, max_width=800, max_height=800)
            except Exception:
                return None
        return None

    def _probe_url(self, url: str) -> Tuple[bool, Optional[int]]:
        methods = ["HEAD", "GET"]
        for method in methods:
            try:
                response = self.session.request(
                    method,
                    url,
                    allow_redirects=True,
                    stream=True,
                    timeout=PROBE_TIMEOUT,
                )
                status = response.status_code
                response.close()
                if status is not None and status < 400:
                    return True, status
            except requests.RequestException:
                status = None
        return False, status if "status" in locals() else None

    def _fetch_google_photos(self, place_id: str, max_results: int) -> List[Dict]:
        params = {"place_id": place_id, "fields": "photo", "key": self.google_api_key}
        try:
            resp = self.session.get(
                self.place_details_url, params=params, timeout=PROBE_TIMEOUT
            )
            if resp.status_code != 200:
                logger.warning(
                    "Place Details %s returned %s", place_id, resp.status_code
                )
                return []

            data = resp.json()
            photos = data.get("result", {}).get("photos", []) or []
            formatted: List[Dict] = []
            for photo in photos:
                ref = photo.get("photo_reference")
                if not ref:
                    continue
                new_entry = {
                    "photo_reference": ref,
                    "width": photo.get("width"),
                    "height": photo.get("height"),
                    "html_attributions": photo.get("html_attributions"),
                }
                try:
                    new_entry["photo_url"] = self.photo_generator.generate_photo_url(
                        ref, max_width=800, max_height=800
                    )
                except Exception:
                    pass
                formatted.append(new_entry)
                if len(formatted) >= max_results:
                    break
            return formatted
        except requests.RequestException as exc:
            logger.warning("Error while calling Place Details: %s", exc)
            return []

    def _update_supabase_photos(self, attraction_id: str, photos: List[Dict]) -> None:
        payload = {
            "photos": photos,
            "updated_at": datetime.now().isoformat(),
        }
        self.supabase.table("attractions").update(payload).eq("id", attraction_id).execute()


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check attraction images and replace broken ones via Google Places."
    )
    parser.add_argument(
        "--city-id",
        help="UUID of a city to inspect (otherwise scans every attraction).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit the number of attractions inspected (quick tests).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply updates in Supabase (default: dry-run).",
    )
    parser.add_argument(
        "--max-new-photos",
        type=int,
        default=MAX_DEFAULT_NEW_PHOTOS,
        help="Maximum number of new Google photos to fetch per attraction (default: 3).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)

    migrator = SupabaseMigrator()
    if not migrator.supabase:
        print("Supabase is not configured - check SUPABASE_URL/SUPABASE_SERVICE_KEY.")
        return 1

    try:
        photo_generator = GooglePhotoURLGenerator()
    except Exception as exc:
        print(f"Unable to initialize GooglePhotoURLGenerator: {exc}")
        return 1

    auditor = AttractionImageAuditor(migrator.supabase, photo_generator)

    counters = auditor.audit(
        city_id=args.city_id,
        limit=args.limit,
        apply_changes=args.apply,
        max_new_photos=args.max_new_photos,
    )

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(
        f"{mode} finished - attractions: {counters['total']} | "
        f"with photos: {counters['with_photos']} | "
        f"ok: {counters['ok']} | "
        f"broken: {counters['broken']} | "
        f"missing place_id: {counters['missing_place_id']} | "
        f"updated: {counters['updated']}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
