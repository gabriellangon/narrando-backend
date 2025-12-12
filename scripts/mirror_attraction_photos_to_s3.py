"""
Mirror Google Place photos to S3 and update Supabase.

Usage:
    python3 scripts/mirror_attraction_photos_to_s3.py [--city-id UUID] [--limit N] [--max-photos N] [--workers N] [--apply]

Behavior:
    - Dry-run by default (no changes in Supabase/S3).
    - For chaque attraction:
        * Vérifie les photos existantes (HEAD/GET).
        * Si une photo est accessible, elle est téléchargée, optimisée (si Pillow dispo) et poussée sur S3.
        * Si aucune photo valide (ou pas assez), récupère de nouvelles photos Google (Place Details), les pousse sur S3.
        * Met à jour Supabase avec les URLs S3 (champ photos) quand --apply est présent.
    - Nettoie les fichiers locaux immédiatement après upload.

Env requis:
    SUPABASE_URL, SUPABASE_SERVICE_KEY
    GOOGLE_PLACES_API_KEY
    AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION (ou defaults), AWS_S3_BUCKET
"""
from __future__ import annotations

import argparse
import io
import os
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import boto3
import requests

# Permet l'import des modules du repo
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if REPO_ROOT not in sys.path:
    sys.path.append(REPO_ROOT)

from database.migrate_to_supabase import SupabaseMigrator  # noqa: E402
from utils.photo_url_generator import GooglePhotoURLGenerator  # noqa: E402
from utils.logging_config import get_logger  # noqa: E402

logger = get_logger(__name__)

PAGE_SIZE = 200
PROBE_TIMEOUT = 8
DOWNLOAD_TIMEOUT = 15
DEFAULT_MAX_PHOTOS = 1
DEFAULT_WORKERS = 6
MAX_PHOTO_SIZE = 1600  # pixels (si Pillow dispo)
JPEG_QUALITY = 80


def _chunk(seq: Sequence, size: int) -> Iterable[List]:
    for idx in range(0, len(seq), size):
        yield list(seq[idx : idx + size])


def _optional_optimize_jpeg(raw_bytes: bytes) -> bytes:
    """
    Essaie de réduire la taille (max MAX_PHOTO_SIZE, qualité JPEG_QUALITY) si Pillow est disponible.
    Retourne les bytes d'origine en cas d'absence ou d'erreur.
    """
    try:
        from PIL import Image  # type: ignore
    except Exception:
        return raw_bytes

    try:
        with Image.open(io.BytesIO(raw_bytes)) as img:
            img = img.convert("RGB")
            img.thumbnail((MAX_PHOTO_SIZE, MAX_PHOTO_SIZE))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
            return buf.getvalue()
    except Exception:
        return raw_bytes


class S3Uploader:
    def __init__(self, bucket: str, region_name: Optional[str] = None):
        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            aws_session_token=os.getenv("AWS_SESSION_TOKEN"),
            region_name=region_name or os.getenv("AWS_REGION", "us-east-1"),
        )
        # Some buckets disable ACLs (Object Ownership: BucketOwnerEnforced).
        # If you need a specific ACL, set S3_OBJECT_ACL, otherwise we omit ACL.
        self.object_acl = os.getenv("S3_OBJECT_ACL")

    def put_image(self, key: str, data: bytes) -> str:
        kwargs = {
            "Bucket": self.bucket,
            "Key": key,
            "Body": data,
            "ContentType": "image/jpeg",
        }
        if self.object_acl:
            kwargs["ACL"] = self.object_acl

        self.client.put_object(**kwargs)
        return f"https://{self.bucket}.s3.amazonaws.com/{key}"


class AttractionPhotoMirrorer:
    def __init__(
        self,
        supabase_client,
        s3_uploader: S3Uploader,
        google_key: str,
        max_photos: int = DEFAULT_MAX_PHOTOS,
        workers: int = DEFAULT_WORKERS,
    ):
        self.supabase = supabase_client
        self.s3 = s3_uploader
        self.google_key = google_key
        self.photo_generator = GooglePhotoURLGenerator()
        # S'assurer que la clé utilisée est bien celle fournie en argument
        self.photo_generator.google_api_key = google_key
        self.max_photos = max_photos
        self.workers = max(workers, 1)
        self.session = requests.Session()

    def mirror(
        self,
        city_id: Optional[str],
        limit: Optional[int],
        apply_changes: bool,
    ) -> Dict[str, int]:
        counters = {
            "total": 0,
            "updated": 0,
            "skipped_no_place": 0,
            "failed": 0,
        }

        attractions = list(self._fetch_attractions(city_id=city_id, limit=limit))
        counters["total"] = len(attractions)

        if not attractions:
            return counters

        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            future_to_attr = {
                executor.submit(
                    self._process_attraction, attr, apply_changes
                ): attr.get("id")
                for attr in attractions
            }
            for future in as_completed(future_to_attr):
                try:
                    status = future.result()
                    if status == "updated":
                        counters["updated"] += 1
                    elif status == "skipped_no_place":
                        counters["skipped_no_place"] += 1
                except Exception as exc:
                    counters["failed"] += 1
                    logger.warning("Attraction %s failed: %s", future_to_attr[future], exc)

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

    def _process_attraction(self, attraction: Dict, apply_changes: bool) -> str:
        place_id = attraction.get("place_id")
        name = attraction.get("name", "Unknown")

        if not place_id:
            logger.info("Skipping %s (no place_id)", name)
            return "skipped_no_place"

        photos = self._normalize_photos(attraction.get("photos"))
        desired = max(self.max_photos, 1)

        candidates: List[Dict] = []

        # Vérifier les photos existantes
        for photo in photos:
            if len(candidates) >= desired:
                break
            url = self._resolve_photo_url(photo)
            if not url:
                continue
            ok, _ = self._probe_url(url)
            if ok:
                ph = dict(photo)
                ph["_source_url"] = url
                candidates.append(ph)

        # Compléter avec de nouvelles photos Google si besoin
        if len(candidates) < desired:
            needed = desired - len(candidates)
            new_google = self._fetch_google_photos(place_id, max_results=needed)
            for photo in new_google:
                if len(candidates) >= desired:
                    break
                photo["_source_url"] = photo.get("photo_url") or self._resolve_photo_url(photo)
                if photo["_source_url"]:
                    candidates.append(photo)

        if not candidates:
            logger.info("No valid photos for %s (%s)", name, place_id)
            return "noop"

        uploaded_photos: List[Dict] = []
        changed = False

        for idx, photo in enumerate(candidates[:desired]):
            src = photo.get("_source_url")
            if not src:
                continue
            content = self._download(src)
            if not content:
                continue
            optimized = _optional_optimize_jpeg(content)
            key = f"images/attractions/{place_id}/{idx+1}_{uuid.uuid4().hex}.jpg"
            url = self.s3.put_image(key, optimized)

            updated_photo = dict(photo)
            updated_photo.pop("_source_url", None)
            updated_photo["photo_url"] = url
            updated_photo["s3_key"] = key
            updated_photo["storage"] = "s3"
            uploaded_photos.append(updated_photo)

        if not uploaded_photos:
            logger.info("No uploads for %s (%s)", name, place_id)
            return "noop"

        # Detect change
        if uploaded_photos != photos[: len(uploaded_photos)]:
            changed = True

        if changed and apply_changes:
            self.supabase.table("attractions").update(
                {
                    "photos": uploaded_photos,
                    "updated_at": datetime.now().isoformat(),
                }
            ).eq("id", attraction.get("id")).execute()
            logger.info(
                "Updated %s (%s): %s photos -> S3",
                name,
                attraction.get("id"),
                len(uploaded_photos),
            )
            return "updated"

        if changed:
            logger.info(
                "DRY-RUN: %s would be updated with %s photos",
                name,
                len(uploaded_photos),
            )
        return "noop"

    def _resolve_photo_url(self, photo: Dict) -> Optional[str]:
        url = photo.get("photo_url") or photo.get("url")
        if url:
            return url
        ref = photo.get("photo_reference")
        if ref:
            try:
                return self.photo_generator.generate_photo_url(
                    ref, max_width=800, max_height=800
                )
            except Exception:
                return None
        return None

    def _probe_url(self, url: str) -> Tuple[bool, Optional[int]]:
        for method in ("HEAD", "GET"):
            try:
                resp = self.session.request(
                    method,
                    url,
                    allow_redirects=True,
                    timeout=PROBE_TIMEOUT,
                    stream=True,
                )
                status = resp.status_code
                resp.close()
                if status is not None and status < 400:
                    return True, status
            except requests.RequestException:
                status = None
        return False, None

    def _download(self, url: str) -> Optional[bytes]:
        try:
            resp = self.session.get(url, timeout=DOWNLOAD_TIMEOUT)
            if resp.status_code == 200:
                return resp.content
        except requests.RequestException:
            return None
        return None

    def _fetch_google_photos(self, place_id: str, max_results: int) -> List[Dict]:
        details_url = "https://maps.googleapis.com/maps/api/place/details/json"
        params = {"place_id": place_id, "fields": "photo", "key": self.google_key}
        try:
            resp = self.session.get(details_url, params=params, timeout=PROBE_TIMEOUT)
            if resp.status_code != 200:
                logger.warning("Place Details %s returned %s", place_id, resp.status_code)
                return []
            data = resp.json()
            photos = data.get("result", {}).get("photos", []) or []
            formatted: List[Dict] = []
            for photo in photos:
                ref = photo.get("photo_reference")
                if not ref:
                    continue
                url = self.photo_generator.generate_photo_url(ref, max_width=800, max_height=800)
                formatted.append(
                    {
                        "photo_reference": ref,
                        "width": photo.get("width"),
                        "height": photo.get("height"),
                        "html_attributions": photo.get("html_attributions"),
                        "photo_url": url,
                    }
                )
                if len(formatted) >= max_results:
                    break
            return formatted
        except requests.RequestException as exc:
            logger.warning("Error fetching Place Details for %s: %s", place_id, exc)
            return []

    def _normalize_photos(self, photos: Optional[object]) -> List[Dict]:
        if not photos or not isinstance(photos, list):
            return []
        return [p for p in photos if isinstance(p, dict)]


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mirror attraction photos to S3 and update Supabase."
    )
    parser.add_argument("--city-id", help="UUID d'une ville à traiter (sinon toutes).")
    parser.add_argument("--limit", type=int, help="Limiter le nombre d'attractions traitées.")
    parser.add_argument(
        "--max-photos",
        type=int,
        default=DEFAULT_MAX_PHOTOS,
        help="Nombre maximum de photos à conserver par attraction (défaut: 1).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help="Nombre de threads de téléchargement (défaut: 6).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Applique les mises à jour dans Supabase et upload S3 (sinon dry-run).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)

    migrator = SupabaseMigrator()
    if not migrator.supabase:
        print("Supabase non configuré – vérifier SUPABASE_URL/SUPABASE_SERVICE_KEY.")
        return 1

    bucket = os.getenv("AWS_S3_BUCKET")
    if not bucket:
        print("AWS_S3_BUCKET manquant.")
        return 1

    google_key = os.getenv("GOOGLE_PLACES_API_KEY")
    if not google_key:
        print("GOOGLE_PLACES_API_KEY manquant.")
        return 1

    s3_uploader = S3Uploader(bucket=bucket)

    mirrorer = AttractionPhotoMirrorer(
        supabase_client=migrator.supabase,
        s3_uploader=s3_uploader,
        google_key=google_key,
        max_photos=args.max_photos,
        workers=args.workers,
    )

    counters = mirrorer.mirror(
        city_id=args.city_id,
        limit=args.limit,
        apply_changes=args.apply,
    )

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(
        f"{mode} terminé – attractions: {counters['total']} | "
        f"mises à jour: {counters['updated']} | "
        f"skipped (no place_id): {counters['skipped_no_place']} | "
        f"échecs: {counters['failed']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
