"""
Force walking_paths.path_coordinates to start/end exactly at the attraction coordinates.

Usage:
    python scripts/repair_walking_paths.py --tour-id <uuid> [--apply]
    python scripts/repair_walking_paths.py --all --apply
"""
from __future__ import annotations

import argparse
from typing import Dict, Iterable, List, Optional, Sequence

from database.migrate_to_supabase import SupabaseMigrator
from utils.logging_config import get_logger
from utils.path_validation import ensure_path_endpoints

logger = get_logger(__name__)
FIELDS = "id, tour_id, from_attraction_id, to_attraction_id, path_coordinates"


def _chunk(seq: Sequence[str], size: int) -> Iterable[List[str]]:
    for idx in range(0, len(seq), size):
        yield list(seq[idx : idx + size])


class WalkingPathRepairer:
    def __init__(self, supabase_client):
        self.supabase = supabase_client

    def repair(self, tour_ids: Optional[List[str]] = None, apply_changes: bool = False) -> Dict[str, int]:
        rows = self._fetch_paths(tour_ids)
        if not rows:
            logger.info("Aucun walking_path trouvé pour les critères fournis.")
            return {"processed": 0, "updated": 0, "pending_updates": 0, "skipped": 0}

        attraction_ids = self._collect_attraction_ids(rows)
        attractions = self._fetch_attractions(attraction_ids)

        updated = 0
        pending = 0
        skipped = 0

        for row in rows:
            origin = attractions.get(row.get("from_attraction_id"))
            destination = attractions.get(row.get("to_attraction_id"))

            if not origin or not destination:
                skipped += 1
                logger.warning(
                    "Attractions manquantes pour walking_path %s (tour %s)",
                    row.get("id"),
                    row.get("tour_id"),
                )
                continue

            normalized = ensure_path_endpoints(row.get("path_coordinates"), origin, destination)
            current_points = self._to_points(row.get("path_coordinates"))

            if self._points_equal(current_points, normalized):
                continue

            pending += 1
            logger.debug(
                "Segment %s nécessite une mise à jour (%s → %s)",
                row.get("id"),
                row.get("from_attraction_id"),
                row.get("to_attraction_id"),
            )

            if apply_changes:
                self.supabase.table("walking_paths").update(
                    {"path_coordinates": normalized}
                ).eq("id", row["id"]).execute()
                updated += 1

        return {
            "processed": len(rows),
            "updated": updated,
            "pending_updates": pending,
            "skipped": skipped,
        }

    def _fetch_paths(self, tour_ids: Optional[List[str]]) -> List[Dict]:
        if tour_ids:
            rows: List[Dict] = []
            for chunk in _chunk(tour_ids, 50):
                query = self.supabase.table("walking_paths").select(FIELDS)
                if len(chunk) == 1:
                    query = query.eq("tour_id", chunk[0])
                else:
                    query = query.in_("tour_id", chunk)
                result = query.execute()
                rows.extend(result.data or [])
            return rows

        # Récupérer toutes les lignes par pagination
        rows: List[Dict] = []
        start = 0
        page_size = 500

        while True:
            result = (
                self.supabase.table("walking_paths")
                .select(FIELDS)
                .range(start, start + page_size - 1)
                .execute()
            )
            batch = result.data or []
            rows.extend(batch)
            if len(batch) < page_size:
                break
            start += page_size

        return rows

    @staticmethod
    def _collect_attraction_ids(rows: List[Dict]) -> List[str]:
        ids = set()
        for row in rows:
            from_id = row.get("from_attraction_id")
            to_id = row.get("to_attraction_id")
            if from_id:
                ids.add(from_id)
            if to_id:
                ids.add(to_id)
        return list(ids)

    def _fetch_attractions(self, attraction_ids: List[str]) -> Dict[str, Dict[str, float]]:
        if not attraction_ids:
            return {}

        mapping: Dict[str, Dict[str, float]] = {}
        for chunk in _chunk(attraction_ids, 100):
            result = (
                self.supabase.table("attractions")
                .select("id, lat, lng")
                .in_("id", chunk)
                .execute()
            )
            for row in result.data or []:
                try:
                    mapping[row["id"]] = {
                        "lat": float(row["lat"]),
                        "lng": float(row["lng"]),
                    }
                except (KeyError, TypeError, ValueError):
                    logger.warning("Coordonnées invalides pour attraction %s", row.get("id"))
        return mapping

    @staticmethod
    def _to_points(path_coordinates: Optional[List[Dict]]) -> List[Dict[str, float]]:
        if not path_coordinates:
            return []

        points: List[Dict[str, float]] = []
        for coord in path_coordinates:
            try:
                points.append({"lat": float(coord["lat"]), "lng": float(coord["lng"])})
            except (KeyError, TypeError, ValueError):
                continue
        return points

    @staticmethod
    def _points_equal(a: List[Dict[str, float]], b: List[Dict[str, float]], tolerance: float = 1e-9) -> bool:
        if len(a) != len(b):
            return False
        return all(
            abs(first["lat"] - second["lat"]) <= tolerance and
            abs(first["lng"] - second["lng"]) <= tolerance
            for first, second in zip(a, b)
        )


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Répare les walking_paths invalides dans Supabase.")
    parser.add_argument(
        "--tour-id",
        dest="tour_ids",
        action="append",
        help="UUID d'un tour à réparer (répéter pour plusieurs tours)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Réparer tous les tours (peut être long).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Applique les corrections (sinon dry-run).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)

    if not args.all and not args.tour_ids:
        print("❌ Fournir au moins un --tour-id ou utiliser --all.")
        return 1

    migrator = SupabaseMigrator()
    if not migrator.supabase:
        print("❌ Supabase non configuré – vérifier SUPABASE_URL/SUPABASE_SERVICE_KEY.")
        return 1

    repairer = WalkingPathRepairer(migrator.supabase)
    result = repairer.repair(args.tour_ids if not args.all else None, apply_changes=args.apply)

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(
        f"{mode} terminé – segments inspectés: {result['processed']} | "
        f"à corriger: {result['pending_updates']} | "
        f"corrigés: {result['updated']} | "
        f"ignorés: {result['skipped']}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
