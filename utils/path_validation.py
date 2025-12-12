"""
Utilities to keep walking path coordinates consistent with attraction locations.
"""
from __future__ import annotations

from typing import Dict, List, Optional

Coordinate = Dict[str, float]


def _to_point(raw: Dict[str, float] | None) -> Optional[Coordinate]:
    """
    Convert any mapping containing lat/lng keys to a float-based coordinate.
    """
    if not isinstance(raw, dict):
        return None

    try:
        lat = float(raw["lat"])
        lng = float(raw["lng"])
    except (KeyError, TypeError, ValueError):
        return None

    return {"lat": lat, "lng": lng}


def _normalize_coordinates(path_coordinates: List[Dict[str, float]] | None) -> List[Coordinate]:
    """
    Convert every point in the path to floats and drop malformed ones.
    """
    normalized: List[Coordinate] = []

    if not path_coordinates:
        return normalized

    for raw_point in path_coordinates:
        point = _to_point(raw_point)
        if point:
            normalized.append(point)

    return normalized


def _points_match(a: Coordinate, b: Coordinate, tolerance: float = 1e-9) -> bool:
    return abs(a["lat"] - b["lat"]) <= tolerance and abs(a["lng"] - b["lng"]) <= tolerance


def _deduplicate(points: List[Coordinate]) -> List[Coordinate]:
    """
    Remove consecutive duplicates that might appear after forcing endpoints.
    """
    if not points:
        return points

    deduped: List[Coordinate] = [points[0]]
    for point in points[1:]:
        if not _points_match(deduped[-1], point):
            deduped.append(point)
    return deduped


def ensure_path_endpoints(
    path_coordinates: List[Dict[str, float]] | None,
    origin: Dict[str, float] | None,
    destination: Dict[str, float] | None,
) -> List[Coordinate]:
    """
    Ensure the polyline starts exactly at the origin coordinates and ends at the destination.

    If the stored path is empty or malformed we fall back to a simple straight line.
    """
    origin_point = _to_point(origin)
    destination_point = _to_point(destination)

    if not origin_point or not destination_point:
        return _normalize_coordinates(path_coordinates)

    coords = _normalize_coordinates(path_coordinates)

    if not coords:
        return [origin_point, destination_point]

    coords[0] = origin_point
    if len(coords) == 1:
        coords.append(destination_point)
    else:
        coords[-1] = destination_point

    return _deduplicate(coords)
