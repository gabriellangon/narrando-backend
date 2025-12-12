import json
import os
from datetime import datetime
from functools import wraps
from typing import Dict, List
import logging
from postgrest.exceptions import APIError

from flask import Blueprint, abort, jsonify, redirect, render_template, request, url_for

logger = logging.getLogger(__name__)


def create_admin_blueprint(api_client):
    """
    Crée le blueprint d'administration (UI + API JSON).
    """
    admin_bp = Blueprint(
        "admin",
        __name__,
        template_folder="templates",
        static_folder="static",
        url_prefix="/admin"
    )
    admin_token = os.getenv("API_TOKEN") or os.getenv("ADMIN_TOKEN")

    def _expected_token() -> str:
        if not admin_token:
            abort(503, description="API_TOKEN (ou ADMIN_TOKEN) non configuré.")
        return admin_token

    def _extract_token() -> str:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header.replace("Bearer ", "", 1).strip()
        if request.cookies.get("admin_token"):
            return request.cookies.get("admin_token", "")
        body = request.get_json(silent=True) or {}
        if isinstance(body, dict):
            token_from_body = body.get("token")
            if token_from_body:
                return str(token_from_body)
        return ""

    def require_admin_token():
        provided = _extract_token()
        expected = _expected_token()
        if not provided or provided != expected:
            abort(401, description="Token admin requis ou invalide.")

    def admin_api_protected(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            require_admin_token()
            return func(*args, **kwargs)
        return wrapper

    def require_supabase():
        migrator = getattr(api_client, "migrator", None)
        supabase = getattr(migrator, "supabase", None)
        if not supabase:
            abort(503, description="Supabase non configuré – merci de renseigner SUPABASE_URL/SUPABASE_SERVICE_KEY.")
        return supabase

    def require_route_optimizer():
        optimizer = getattr(api_client, "route_optimizer", None)
        if not optimizer:
            abort(503, description="RouteOptimizer indisponible – génération des chemins impossible.")
        return optimizer

    def fetch_city_or_404(supabase, city_id: str) -> Dict:
        result = supabase.table("cities").select("id, city, country").eq("id", city_id).execute()
        rows = result.data or []
        if not rows:
            abort(404, description="Ville introuvable.")
        return rows[0]

    def fetch_tour_or_404(supabase, tour_id: str) -> Dict:
        result = (
            supabase.table("guided_tours")
            .select("id, city_id, tour_name, total_distance, estimated_walking_time, point_count, start_point, end_point")
            .eq("id", tour_id)
            .execute()
        )
        rows = result.data or []
        if not rows:
            abort(404, description="Tour introuvable.")
        return rows[0]

    def build_attraction_map(supabase, attraction_ids: List[str]) -> Dict[str, Dict]:
        if not attraction_ids:
            abort(400, description="Liste des attractions vide.")
        result = (
            supabase.table("attractions")
            .select("id, name, formatted_address, lat, lng")
            .in_("id", attraction_ids)
            .execute()
        )
        rows = result.data or []
        found_ids = {row["id"] for row in rows}
        missing = [attr_id for attr_id in attraction_ids if attr_id not in found_ids]
        if missing:
            abort(400, description=f"Attractions introuvables: {', '.join(missing)}")
        for row in rows:
            # Supabase renvoie des Decimal/str, garantir float
            row["lat"] = float(row["lat"])
            row["lng"] = float(row["lng"])
        return {row["id"]: row for row in rows}

    def fetch_existing_tour_points(supabase, tour_id: str) -> List[Dict]:
        result = (
            supabase.table("tour_points")
            .select("id, tour_id, attraction_id, point_order, global_index, created_at")
            .eq("tour_id", tour_id)
            .order("point_order", desc=False)
            .execute()
        )
        return result.data or []

    def fetch_existing_walking_paths(supabase, tour_id: str) -> List[Dict]:
        result = (
            supabase.table("walking_paths")
            .select("id, tour_id, from_attraction_id, to_attraction_id, path_coordinates, created_at")
            .eq("tour_id", tour_id)
            .order("created_at", desc=False)
            .execute()
        )
        return result.data or []

    def compute_walking_payload(route_optimizer, attraction_sequence: List[str], attractions: Dict[str, Dict]) -> Dict:
        """
        Prépare les segments + stats sans toucher à la base.
        """
        walking_rows = []
        total_distance = 0
        total_minutes = 0

        for i in range(len(attraction_sequence) - 1):
            current_id = attraction_sequence[i]
            next_id = attraction_sequence[i + 1]
            origin = {"lat": attractions[current_id]["lat"], "lng": attractions[current_id]["lng"]}
            destination = {"lat": attractions[next_id]["lat"], "lng": attractions[next_id]["lng"]}

            distance = route_optimizer._get_walking_distance_cached(origin, destination)  # type: ignore[attr-defined]
            if distance is None:
                abort(502, description="Impossible de récupérer la distance de marche via Google Directions.")

            minutes = route_optimizer._distance_to_walking_minutes(distance)  # type: ignore[attr-defined]
            path_coordinates = route_optimizer._get_detailed_walking_path(origin, destination)  # type: ignore[attr-defined]

            walking_rows.append({
                "from_attraction_id": current_id,
                "to_attraction_id": next_id,
                "path_coordinates": path_coordinates,
                "created_at": datetime.utcnow().isoformat()
            })

            total_distance += int(distance)
            total_minutes += minutes

        return {
            "rows": walking_rows,
            "total_distance": total_distance,
            "total_minutes": total_minutes
        }

    def persist_tour_order(supabase, tour_id: str, new_points: List[Dict], walking_payload: Dict, stats: Dict, rollback_data: Dict):
        """
        Applique les changements dans la base en essayant de restaurer l'état initial en cas d'échec.
        """
        previous_points = rollback_data.get("tour_points", [])
        previous_paths = rollback_data.get("walking_paths", [])
        previous_meta = rollback_data.get("tour_meta", {})

        try:
            supabase.table("tour_points").delete().eq("tour_id", tour_id).execute()
            insert_result = supabase.table("tour_points").insert(new_points).execute()
            if insert_result.data is None:
                raise RuntimeError("Insertion des nouveaux points échouée.")

            supabase.table("walking_paths").delete().eq("tour_id", tour_id).execute()
            if walking_payload["rows"]:
                insert_paths = (
                    supabase.table("walking_paths")
                    .insert([
                        {
                            "tour_id": tour_id,
                            **row
                        }
                        for row in walking_payload["rows"]
                    ])
                    .execute()
                )
                if insert_paths.data is None:
                    raise RuntimeError("Insertion des walking paths échouée.")

            update_payload = {
                "point_count": stats["point_count"],
                "total_distance": stats["total_distance"],
                "estimated_walking_time": stats["estimated_walking_time"],
                "start_point": stats["start_point"],
                "end_point": stats["end_point"],
                "updated_at": datetime.utcnow().isoformat()
            }
            supabase.table("guided_tours").update(update_payload).eq("id", tour_id).execute()

        except Exception as err:
            # Tentative de restauration
            try:
                supabase.table("tour_points").delete().eq("tour_id", tour_id).execute()
                if previous_points:
                    supabase.table("tour_points").insert(previous_points).execute()

                supabase.table("walking_paths").delete().eq("tour_id", tour_id).execute()
                if previous_paths:
                    supabase.table("walking_paths").insert(previous_paths).execute()

                if previous_meta:
                    supabase.table("guided_tours").update(previous_meta).eq("id", tour_id).execute()
            finally:
                abort(500, description=f"Échec sauvegarde de l'ordre: {err}")

    def recompute_tour(tour_id: str, attraction_sequence: List[str]):
        supabase = require_supabase()
        route_optimizer = require_route_optimizer()

        attractions = build_attraction_map(supabase, attraction_sequence)
        walking_payload = compute_walking_payload(route_optimizer, attraction_sequence, attractions)

        stats = {
            "point_count": len(attraction_sequence),
            "total_distance": walking_payload["total_distance"],
            "estimated_walking_time": walking_payload["total_minutes"],
            "start_point": attractions[attraction_sequence[0]]["name"] if attraction_sequence else None,
            "end_point": attractions[attraction_sequence[-1]]["name"] if len(attraction_sequence) > 1 else None
        }

        new_points = []
        now_iso = datetime.utcnow().isoformat()
        for idx, attraction_id in enumerate(attraction_sequence):
            new_points.append({
                "tour_id": tour_id,
                "attraction_id": attraction_id,
                "point_order": idx + 1,
                "global_index": idx,
                "created_at": now_iso
            })

        rollback_data = {
            "tour_points": fetch_existing_tour_points(supabase, tour_id),
            "walking_paths": fetch_existing_walking_paths(supabase, tour_id),
            "tour_meta": fetch_tour_or_404(supabase, tour_id)
        }

        persist_tour_order(
            supabase,
            tour_id,
            new_points,
            walking_payload,
            stats,
            rollback_data
        )

    # -------------------- Routes UI -------------------- #
    @admin_bp.route("/", methods=["GET"])
    def admin_home():
        # Exige le token pour l'UI également
        try:
            require_admin_token()
        except Exception:
            return redirect(url_for("admin.login_page"))

        supabase_ready = bool(getattr(getattr(api_client, "migrator", None), "supabase", None))
        google_maps_key = os.getenv("GOOGLE_MAPS_JS_API_KEY", "")
        return render_template(
            "admin/index.html",
            supabase_ready=supabase_ready,
            google_maps_key=google_maps_key
        )

    @admin_bp.route("/users", methods=["GET"])
    def users_page():
        try:
            require_admin_token()
        except Exception:
            return redirect(url_for("admin.login_page"))

        supabase_ready = bool(getattr(getattr(api_client, "migrator", None), "supabase", None))
        return render_template(
            "admin/users.html",
            supabase_ready=supabase_ready
        )

    @admin_bp.route("/login", methods=["GET", "POST"])
    def login_page():
        _expected_token()  # vérifie config
        error = None
        if request.method == "POST":
            body = request.get_json(silent=True) or {}
            submitted = request.form.get("token") or body.get("token")
            if submitted and submitted == _expected_token():
                response = redirect(url_for("admin.admin_home"))
                response.set_cookie("admin_token", submitted, httponly=True, samesite="Lax")
                return response
            error = "Token invalide."
        return render_template("admin/login.html", error=error)

    # -------------------- API JSON -------------------- #
    @admin_bp.route("/api/cities", methods=["GET"])
    @admin_api_protected
    def list_cities():
        supabase = require_supabase()
        result = (
            supabase.table("cities")
            .select("id, city, country, country_iso_code")
            .order("city")
            .execute()
        )
        records = result.data or []
        return jsonify({
            "cities": records,
            "count": len(records)
        })

    @admin_bp.route("/api/cities/<city_id>/tours", methods=["GET"])
    @admin_api_protected
    def list_city_tours(city_id: str):
        supabase = require_supabase()
        fetch_city_or_404(supabase, city_id)
        result = (
            supabase.table("guided_tours")
            .select("id, tour_name, point_count, total_distance, estimated_walking_time, updated_at")
            .eq("city_id", city_id)
            .order("tour_name")
            .execute()
        )
        tours = result.data or []
        return jsonify({"tours": tours, "count": len(tours)})

    @admin_bp.route("/api/tours/<tour_id>", methods=["GET"])
    @admin_api_protected
    def get_tour_detail(tour_id: str):
        supabase = require_supabase()
        result = supabase.rpc(
            "get_complete_tour_with_walking_paths",
            {"tour_id_param": tour_id, "language_code_param": "en"}
        ).execute()
        tour_data = result.data
        if not tour_data:
            abort(404, description="Tour complet introuvable.")
        return jsonify({"tour": tour_data})

    @admin_bp.route("/api/tours/<tour_id>/reorder", methods=["POST"])
    @admin_api_protected
    def reorder_tour(tour_id: str):
        payload = request.get_json(silent=False) or {}
        ordered_ids = payload.get("ordered_attraction_ids")
        if not isinstance(ordered_ids, list) or not ordered_ids:
            abort(400, description="ordered_attraction_ids doit être une liste non vide.")

        supabase = require_supabase()
        existing_points = fetch_existing_tour_points(supabase, tour_id)
        if not existing_points:
            abort(400, description="Aucun point n'est associé à ce tour.")

        original_ids = [row["attraction_id"] for row in existing_points]
        if set(original_ids) != set(ordered_ids):
            abort(400, description="Les attractions ne correspondent pas à l'état actuel du tour.")

        recompute_tour(tour_id, ordered_ids)

        return get_tour_detail(tour_id)

    @admin_bp.route("/api/attractions/<attraction_id>", methods=["DELETE"])
    @admin_api_protected
    def delete_attraction(attraction_id: str):
        supabase = require_supabase()
        # Récupérer les tours impactés
        points = (
            supabase.table("tour_points")
            .select("tour_id, point_order")
            .eq("attraction_id", attraction_id)
            .execute()
        ).data or []

        # Supprimer l'attraction (cascade sur translations, walking_paths liés)
        delete_result = (
            supabase.table("attractions")
            .delete()
            .eq("id", attraction_id)
            .execute()
        )
        if not delete_result.data:
            abort(404, description="Attraction introuvable ou déjà supprimée.")

        impacted_tours = sorted({row["tour_id"] for row in points if row.get("tour_id")})
        for tour_id in impacted_tours:
            remaining = (
                supabase.table("tour_points")
                .select("attraction_id")
                .eq("tour_id", tour_id)
                .order("point_order")
                .execute()
            ).data or []
            sequence = [row["attraction_id"] for row in remaining]
            if sequence:
                recompute_tour(tour_id, sequence)
            else:
                # Tour vidé : nettoyer stats
                supabase.table("guided_tours").update({
                    "point_count": 0,
                    "total_distance": 0,
                    "estimated_walking_time": 0,
                    "start_point": None,
                    "end_point": None,
                    "updated_at": datetime.utcnow().isoformat()
                }).eq("id", tour_id).execute()
                supabase.table("walking_paths").delete().eq("tour_id", tour_id).execute()

        return jsonify({
            "deleted": attraction_id,
            "impacted_tours": impacted_tours
        })

    # -------------------- API Users Dashboard -------------------- #
    def _fetch_users_basic(supabase, search: str, limit: int = 50):
        query = (
            supabase.table("users")
            .select("id, email, first_name, last_name, created_at, last_login, credits, revenuecat_user_id")
            .order("created_at", desc=True)
        )
        if search:
            # Utilise OR case-insensitive sur email / prénom / nom
            or_filter = f"email.ilike.*{search}*,first_name.ilike.*{search}*,last_name.ilike.*{search}*"
            query = query.or_(or_filter)  # type: ignore[attr-defined]
        if limit and limit > 0:
            query = query.range(0, limit - 1)
        return query.execute().data or []

    def _map_purchases_by_id(supabase, table_name: str, purchase_ids: List[str]):
        if not purchase_ids:
            return {}
        result = (
            supabase.table(table_name)
            .select("id, narration_type, language_code, purchase_date, source, quantity_total, quantity_completed, quantity_gifted")
            .in_("id", purchase_ids)
            .execute()
        )
        rows = result.data or []
        return {row["id"]: row for row in rows}

    def _coerce_status_payload(payload) -> Dict:
        """
        Garantit un dict status même si Supabase renvoie une chaîne pseudo-JSON.
        """
        if not payload:
            return {}
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, list):
            return {"items": payload}
        if isinstance(payload, str):
            text = payload.strip()
            if not text:
                return {}
            candidates = [text]
            normalized_quotes = text.replace("'", '"')
            if normalized_quotes != text:
                candidates.append(normalized_quotes)
            python_like = normalized_quotes.replace("None", "null").replace("True", "true").replace("False", "false")
            if python_like != normalized_quotes:
                candidates.append(python_like)
            for candidate in candidates:
                try:
                    parsed = json.loads(candidate)
                    if isinstance(parsed, dict):
                        return parsed
                except Exception:
                    continue
        return {}

    def _compute_tour_status(supabase, tour_entry: Dict, user_id: str, narration_type: str, language_code: str) -> Dict:
        try:
            if tour_entry.get("tour_type") == "custom":
                status_resp = supabase.rpc(
                    "check_user_tour_generation_status",
                    {
                        "tour_id_param": tour_entry["tour_id"],
                        "user_id_param": user_id,
                        "narration_type_param": narration_type,
                        "language_code_param": language_code
                    }
                ).execute()
            else:
                status_resp = supabase.rpc(
                    "check_tour_generation_status",
                    {
                        "tour_id_param": tour_entry["tour_id"],
                        "user_id_param": user_id,
                        "narration_type_param": narration_type,
                        "language_code_param": language_code
                    }
                ).execute()
            return _coerce_status_payload(status_resp.data or {})
        except APIError as api_err:  # supabase-py confond les payloads RPC contenant "message" avec une erreur
            payload = None
            try:
                payload = api_err.args[0]
            except Exception:
                payload = None
            if isinstance(payload, dict) and "status" in payload:
                return payload
            normalized = _coerce_status_payload(payload)
            if normalized:
                return normalized
            logger.info("⚠️ APIError statut génération tour %s: %s", tour_entry.get("tour_id"), api_err)
            return {"status": "unknown", "message": str(api_err)}
        except Exception as rpc_error:  # pragma: no cover - observabilité
            logger.info("⚠️ Impossible de récupérer le statut de génération pour %s: %s", tour_entry.get("tour_id"), rpc_error)
            return {"status": "unknown", "message": str(rpc_error)}

    def _summarize_status(payload, *, already_normalized: bool = False) -> str:
        payload_dict = payload if already_normalized else _coerce_status_payload(payload)
        if not payload_dict:
            return ""
        for key in ("message", "error_message", "status_message"):
            msg = payload_dict.get(key)
            if msg:
                return str(msg)
        parts = []
        if payload_dict.get("status"):
            parts.append(f"Statut: {payload_dict.get('status')}")
        total = payload_dict.get("total_points") or payload_dict.get("total")
        completed = payload_dict.get("completed_points") or payload_dict.get("with_audio")
        if total is not None and completed is not None:
            parts.append(f"{completed}/{total} points avec audio")
        progress = payload_dict.get("progress_percent")
        if progress is not None:
            parts.append(f"Progression: {progress}%")
        if not parts and payload_dict:
            # Fallback: clé=valeur simples
            for k, v in payload_dict.items():
                if isinstance(v, (str, int, float, bool)) and k not in {"status", "message"}:
                    parts.append(f"{k}: {v}")
        return " · ".join(parts)

    def _build_status_info(payload: Dict, language_code: str, narration_type: str) -> Dict:
        normalized = _coerce_status_payload(payload)
        total_points = normalized.get("total_points") or normalized.get("total")
        completed_points = normalized.get("completed_points") or normalized.get("with_audio")
        return {
            "status": normalized.get("status"),
            "message": _summarize_status(normalized, already_normalized=True),
            "total_points": total_points,
            "completed_points": completed_points,
            "progress_percent": normalized.get("progress_percent"),
            "language_code": normalized.get("language_code") or language_code,
            "narration_type": normalized.get("narration_type") or narration_type,
            "requested_at": normalized.get("requested_at"),
            "owned_languages": normalized.get("owned_languages"),
            "user_has_purchase": normalized.get("user_has_purchase"),
            "raw": normalized
        }

    @admin_bp.route("/api/users", methods=["GET"])
    @admin_api_protected
    def list_users():
        supabase = require_supabase()
        search = (request.args.get("search") or "").strip()
        try:
            limit = int(request.args.get("limit", "50"))
        except ValueError:
            limit = 50
        limit = max(1, min(limit, 200))
        users = _fetch_users_basic(supabase, search, limit)
        return jsonify({
            "users": users,
            "count": len(users)
        })

    @admin_bp.route("/api/users/<user_id>", methods=["GET"])
    @admin_api_protected
    def get_user_overview(user_id: str):
        supabase = require_supabase()
        # Fiche user
        user_res = (
            supabase.table("users")
            .select("id, email, first_name, last_name, created_at, last_login, credits, revenuecat_user_id")
            .eq("id", user_id)
            .execute()
        )
        user_rows = user_res.data or []
        if not user_rows:
            abort(404, description="Utilisateur introuvable")
        user_data = user_rows[0]

        # Tours (guided + custom) via RPC union
        tours_res = supabase.rpc(
            "get_user_active_all_tours",
            {"p_user_id": user_id, "p_language_code": "en"}
        ).execute()
        tours = tours_res.data or []

        auto_purchase_ids = [row["purchase_id"] for row in tours if row.get("tour_type") == "auto" and row.get("purchase_id")]
        custom_purchase_ids = [row["purchase_id"] for row in tours if row.get("tour_type") == "custom" and row.get("purchase_id")]

        auto_purchase_map = _map_purchases_by_id(supabase, "tour_purchases", auto_purchase_ids)
        custom_purchase_map = _map_purchases_by_id(supabase, "user_tour_purchases", custom_purchase_ids)

        enriched_tours = []
        for row in tours:
            purchase_meta = {}
            if row.get("tour_type") == "custom":
                purchase_meta = custom_purchase_map.get(row.get("purchase_id"), {})
            else:
                purchase_meta = auto_purchase_map.get(row.get("purchase_id"), {})

            language_code = purchase_meta.get("language_code") or row.get("language_code") or "en"
            narration_type = purchase_meta.get("narration_type") or "standard"
            status_payload = _compute_tour_status(supabase, row, user_id, narration_type, language_code)
            status_info = _build_status_info(status_payload, language_code, narration_type)

            enriched_tours.append({
                "tour_id": row.get("tour_id"),
                "tour_name": row.get("tour_name"),
                "tour_type": row.get("tour_type"),
                "city": row.get("city"),
                "country": row.get("country"),
                "place_id": row.get("place_id"),
                "language_code": language_code,
                "narration_type": narration_type,
                "purchase_id": row.get("purchase_id"),
                "purchase_date": row.get("purchase_date"),
                "source": purchase_meta.get("source") or row.get("source"),
                "quantity_total": purchase_meta.get("quantity_total") or row.get("quantity_total"),
                "quantity_completed": purchase_meta.get("quantity_completed") or row.get("quantity_completed"),
                "quantity_gifted": purchase_meta.get("quantity_gifted") or row.get("quantity_gifted"),
                "total_distance": row.get("total_distance"),
                "estimated_walking_time": row.get("estimated_walking_time"),
                "point_count": row.get("point_count"),
                "first_point_name": row.get("first_point_name"),
                "first_point_address": row.get("first_point_address"),
                "first_point_photos": row.get("first_point_photos"),
                "status_info": status_info
            })

        return jsonify({
            "user": user_data,
            "tours": enriched_tours,
            "tours_count": len(enriched_tours)
        })

    return admin_bp
