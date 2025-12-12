"""
Client Perplexity - Traitement optimisé par lots avec parallélisation
"""
import os
import json
import re
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Any
from dotenv import load_dotenv
from utils.logging_config import get_logger, verbose_logging_enabled

# Charger les variables d'environnement
load_dotenv()

logger = get_logger(__name__)
VERBOSE_LOGS = verbose_logging_enabled()


def _get_timeout_seconds(env_var: str, default: float) -> float:
    raw_value = os.getenv(env_var)
    if not raw_value:
        return default
    try:
        parsed = float(raw_value)
        if parsed <= 0:
            raise ValueError("timeout must be positive")
        return parsed
    except ValueError:
        logger.warning("⚠️ %s invalide (%r), utilisation du défaut: %ss", env_var, raw_value, default)
        return default


PERPLEXITY_TIMEOUT = _get_timeout_seconds("PERPLEXITY_TIMEOUT_SECONDS", 60.0)


class PerplexityClient:
    """
    Client pour l'API Perplexity avec traitement par lots de 5 et parallélisation
    """

    # Types à bannir d'office (services, agences, transports, hébergements)
    BANNED_TYPES = {
        "travel_agency",
        "real_estate_agency",
        "lodging",
        "hotel",
        "restaurant",
        "cafe",
        "bar",
        "store",
        "clothing_store",
        "shopping_mall",
        "department_store",
        "meal_takeaway",
        "meal_delivery",
        "car_rental",
        "tour_operator",
        "tourist_information_center",
        "train_station",
        "bus_station",
        "airport",
        "subway_station",
        "light_rail_station",
        "taxi_stand",
        "gas_station",
        "parking",
        "night_club",
        "gym",
        "spa",
        "beauty_salon"
    }

    def __init__(self, max_workers: int = 5, batch_size: int = 5):
        """
        Initialise le client Perplexity

        Args:
            max_workers: Nombre maximum de threads parallèles
            batch_size: Taille des lots (recommandé: 5)
        """
        self.api_key = os.getenv("PERPLEXITY_API_KEY")
        if not self.api_key:
            raise ValueError("La clé API Perplexity n'est pas définie dans le fichier .env")

        self.base_url = "https://api.perplexity.ai/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        self.max_workers = max_workers
        self.batch_size = batch_size
        log_path = os.getenv("PERPLEXITY_FILTER_LOG", os.path.join("logs", "perplexity_filter.log"))
        abs_path = os.path.abspath(log_path)
        log_dir = os.path.dirname(abs_path)
        if log_dir and not os.path.exists(log_dir):
            try:
                os.makedirs(log_dir, exist_ok=True)
            except OSError as err:
                logger.warning("⚠️ Impossible de créer le dossier de logs (%s): %s. Logging fichier désactivé.", log_dir, err)
                abs_path = None
        self.log_file = abs_path
    
    def filter_attractions(self, attractions: List[Dict[str, Any]], city: str, country: str) -> List[Dict[str, Any]]:
        """
        Filtre les attractions par lots de 5 avec parallélisation
        
        Args:
            attractions: Liste des attractions à filtrer
            city: Nom de la ville
            country: Nom du pays
            
        Returns:
            Liste filtrée des attractions touristiques (sans descriptions)
        """
        if not attractions:
            return []

        # Pré-filtrer les services évidents via types Google
        cleaned_attractions = []
        banned_count = 0
        for attraction in attractions:
            types = {t.lower() for t in attraction.get("types", [])}
            if types & self.BANNED_TYPES:
                banned_count += 1
                continue
            cleaned_attractions.append(attraction)

        if banned_count:
            logger.info("🚫 %s lieux exclus immédiatement (types interdits)", banned_count)

        if not cleaned_attractions:
            logger.warning("❌ Aucune attraction admissible après pré-filtrage.")
            return []

        # Diviser les attractions en lots de 5
        batches = self._create_batches(cleaned_attractions)
        
        logger.info("🚀 Filtrage de %s attractions par lots de %s", len(attractions), self.batch_size)
        logger.info("📦 Nombre de lots: %s", len(batches))
        logger.info("⚡ Threads parallèles: %s", self.max_workers)
        
        # Traitement parallèle des lots
        filtered_attractions = []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Soumettre tous les lots
            future_to_batch = {
                executor.submit(self._process_batch, batch, batch_idx, city, country): (batch, batch_idx)
                for batch_idx, batch in enumerate(batches)
            }
            
            # Récupérer les résultats au fur et à mesure
            for future in as_completed(future_to_batch):
                batch, batch_idx = future_to_batch[future]
                
                try:
                    batch_result = future.result()
                    filtered_attractions.extend(batch_result)
                    logger.debug(
                        "✅ Lot %s/%s terminé - %s attractions conservées",
                        batch_idx + 1,
                        len(batches),
                        len(batch_result),
                    )
                    
                except Exception as e:
                    logger.error("❌ Erreur sur le lot %s: %s", batch_idx + 1, e)
                    logger.debug("🔄 Conservation par défaut du lot %s", batch_idx + 1)
                    filtered_attractions.extend(batch)
        
        logger.info(
            "🎯 Filtrage terminé: %s/%s attractions conservées (avant déduplication)",
            len(filtered_attractions),
            len(cleaned_attractions),
        )
        
        deduped = self._deduplicate_attractions(filtered_attractions)
        if len(deduped) != len(filtered_attractions):
            logger.info("🧼 Déduplication: %s doublon(s) retiré(s)", len(filtered_attractions) - len(deduped))

        return deduped
    
    def _create_batches(self, attractions: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        """
        Divise les attractions en lots de taille batch_size
        """
        batches = []
        for i in range(0, len(attractions), self.batch_size):
            batch = attractions[i:i + self.batch_size]
            batches.append(batch)
        return batches
    
    def _process_batch(self, batch: List[Dict[str, Any]], batch_idx: int, city: str, country: str) -> List[Dict[str, Any]]:
        """
        Traite un lot de 5 attractions
        
        Args:
            batch: Lot d'attractions (max 5)
            batch_idx: Index du lot pour le suivi
            city: Nom de la ville
            country: Nom du pays
            
        Returns:
            Liste filtrée des attractions du lot
        """
        logger.debug("🔄 Traitement du lot %s (%s attractions)...", batch_idx + 1, len(batch))
        
        # Préparer les données du lot
        batch_data = []
        for idx, attraction in enumerate(batch):
            name = attraction.get("name", "")
            types = attraction.get("types", [])
            rating = attraction.get("rating", 0)
            user_ratings_total = attraction.get("user_ratings_total", 0)
            formatted_address = attraction.get("formatted_address", "")
            
            batch_data.append({
                "index": idx,
                "name": name,
                "address": formatted_address,
                "types": types,
                "rating": rating,
                "user_ratings_total": user_ratings_total
            })
        
        # Créer le prompt optimisé pour le lot (SANS description)
        prompt = f"""
As a tourism expert for {city}, {country}, rigorously evaluate these {len(batch)} places to decide if they deserve to be included in a premium walking tour.

{json.dumps(batch_data, ensure_ascii=False, indent=2)}

NON-NEGOTIABLE RULES:
1. The place MUST be physically located inside {city}, {country}. If it is in a suburb or neighboring city, reject it unless it is a world-famous landmark strongly associated with {city}.
2. Only admit PHYSICAL visitable places (monuments, museums, iconic buildings, parks, UNESCO sites, historic squares). Reject any service, business, restaurant, café, hotel, agency, shop, mall, transport service, station, or purely commercial venue.
3. The place must have clear cultural, historical, or architectural value that justifies a dedicated stop on a self-guided tour.
4. If there is any doubt about relevance or location accuracy, reject it.

OUTPUT FORMAT (strict JSON, no prose):
[
  {{"index": 0, "decision": "keep"|"reject", "reason": "very short justification (<25 words)"}}
]

Reasons should mention the decisive criterion (ex: "outside city", "tourist agency", "low cultural value"). Ensure every listed place receives one entry.
"""
        
        # Préparer la requête API
        payload = {
            "model": "sonar",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a highly selective tourism expert. You evaluate the tourist relevance of places and respond ONLY with a JSON array of indices, without any other text."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.1,
            "max_tokens": 200
        }
        
        try:
            # Appel API avec retry
            response = None
            max_retries = 3
            
            for attempt in range(max_retries):
                try:
                    import requests
                    response = requests.post(self.base_url, headers=self.headers, json=payload, timeout=PERPLEXITY_TIMEOUT)
                    
                    if response.status_code == 200:
                        break
                    elif response.status_code == 429:  # Rate limit
                        wait_time = 2 ** attempt  # Backoff exponentiel
                        logger.warning(
                            "⏳ Rate limit - Attente %ss (tentative %s/%s)",
                            wait_time,
                            attempt + 1,
                            max_retries,
                        )
                        time.sleep(wait_time)
                    else:
                        logger.warning(
                            "⚠️ Erreur API %s (tentative %s/%s)",
                            response.status_code,
                            attempt + 1,
                            max_retries,
                        )
                        
                except requests.exceptions.Timeout:
                    logger.warning("⏰ Timeout (tentative %s/%s)", attempt + 1, max_retries)
                    if attempt < max_retries - 1:
                        time.sleep(1)
            
            if not response or response.status_code != 200:
                logger.error("❌ Échec définitif du lot %s", batch_idx + 1)
                return batch  # Retourner le lot original en cas d'échec
            
            # Traiter la réponse
            response_data = response.json()
            content = response_data.get("choices", [{}])[0].get("message", {}).get("content", "[]").strip()
            
            decisions = self._parse_indices_response(content, len(batch))
            self._log_decisions(city, country, batch_idx, batch, decisions)

            filtered_batch = []
            for entry in decisions:
                idx = entry["index"]
                if entry.get("decision") == "keep" and 0 <= idx < len(batch):
                    kept = dict(batch[idx])
                    if entry.get("reason"):
                        kept["filter_reason"] = entry.get("reason")
                    filtered_batch.append(kept)

            return filtered_batch
            
        except Exception as e:
            logger.warning("⚠️ Exception dans le lot %s: %s", batch_idx + 1, e)
            return batch  # Retourner le lot original en cas d'exception
    
    def _parse_indices_response(self, content: str, max_index: int) -> List[dict]:
        """
        Parse la réponse de l'API pour extraire les indices à conserver + raisons
        """
        try:
            # Nettoyer le contenu
            cleaned_content = content.strip()
            if cleaned_content.startswith('```json'):
                cleaned_content = cleaned_content[7:]
            if cleaned_content.endswith('```'):
                cleaned_content = cleaned_content[:-3]
            cleaned_content = cleaned_content.strip()

            # Parser le JSON
            payload = json.loads(cleaned_content)

            # Attendu : liste d'objets {"index": int, "decision": "...", "reason": "..."}
            decisions = []
            if isinstance(payload, list):
                for entry in payload:
                    if (
                        isinstance(entry, dict)
                        and isinstance(entry.get("index"), int)
                        and 0 <= entry["index"] < max_index
                        and entry.get("decision") in {"keep", "reject"}
                    ):
                        decisions.append({
                            "index": entry["index"],
                            "decision": entry["decision"],
                            "reason": entry.get("reason")
                        })
            if decisions:
                return decisions

        except json.JSONDecodeError:
            match = re.search(r'\[[^\]]+\]', content, re.DOTALL)
            if match:
                try:
                    payload = json.loads(match.group(0))
                    decisions = []
                    if isinstance(payload, list):
                        for entry in payload:
                            if (
                                isinstance(entry, dict)
                                and isinstance(entry.get("index"), int)
                                and 0 <= entry["index"] < max_index
                                and entry.get("decision") in {"keep", "reject"}
                            ):
                                decisions.append({
                                    "index": entry["index"],
                                    "decision": entry["decision"],
                                    "reason": entry.get("reason")
                                })
                    if decisions:
                        return decisions
                except Exception:
                    pass

        # En cas d'échec, conserver tous les indices (fallback conservateur)
        logger.warning("⚠️ Impossible de parser la réponse Perplexity: %s...", content[:100])
        return [{"index": i, "decision": "keep", "reason": None} for i in range(max_index)]

    def _log_decisions(self, city: str, country: str, batch_idx: int, batch: List[Dict[str, Any]], decisions: List[Dict[str, Any]]):
        """
        Enregistre les décisions dans un fichier et affiche un récap console.
        """
        timestamp = datetime.utcnow().isoformat() + "Z"
        lines = []
        for entry in decisions:
            idx = entry["index"]
            attraction = batch[idx] if 0 <= idx < len(batch) else {}
            name = attraction.get("name", "Unknown")
            decision = entry.get("decision")
            reason = entry.get("reason")
            if VERBOSE_LOGS:
                logger.debug(
                    "📝 Lot %s – %s: %s (%s)",
                    batch_idx + 1,
                    name,
                    (decision or "UNKNOWN").upper(),
                    reason or "raison inconnue",
                )
            payload = {
                "timestamp": timestamp,
                "city": city,
                "country": country,
                "batch": batch_idx + 1,
                "attraction_name": name,
                "attraction_address": attraction.get("formatted_address"),
                "types": attraction.get("types", []),
                "rating": attraction.get("rating"),
                "user_ratings_total": attraction.get("user_ratings_total"),
                "decision": decision,
                "reason": reason
            }
            lines.append(json.dumps(payload, ensure_ascii=False))

        if not self.log_file:
            return

        try:
            with open(self.log_file, "a", encoding="utf-8") as log_file:
                log_file.write("\n".join(lines) + "\n")
        except Exception as log_error:
            logger.warning("⚠️ Impossible d'écrire le log Perplexity: %s", log_error)

    def _deduplicate_attractions(self, attractions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Supprime les doublons en privilégiant la meilleure note / popularité
        """
        normalized = {}

        for attr in attractions:
            name = attr.get("name", "").strip().lower()
            if not name:
                key = attr.get("place_id") or attr.get("id") or str(id(attr))
            else:
                key = re.sub(r"[^a-z0-9]+", "", name)

            score = self._score_attraction(attr)
            stored = normalized.get(key)
            if not stored or score > stored["__score"]:
                attr_copy = dict(attr)
                attr_copy["__score"] = score
                normalized[key] = attr_copy

        for attr in normalized.values():
            attr.pop("__score", None)

        return list(normalized.values())

    @staticmethod
    def _score_attraction(attraction: Dict[str, Any]) -> float:
        rating = float(attraction.get("rating") or 0)
        reviews = float(attraction.get("user_ratings_total") or 0)
        return rating * 10 + reviews
    
    def get_filtering_stats(self, original_count: int, filtered_count: int) -> Dict[str, Any]:
        """
        Retourne les statistiques du filtrage batch parallélisé
        """
        retention_rate = (filtered_count / original_count) * 100 if original_count > 0 else 0
        
        return {
            "method": "batch_parallel",
            "batch_size": self.batch_size,
            "max_workers": self.max_workers,
            "original_count": original_count,
            "filtered_count": filtered_count,
            "retention_rate": round(retention_rate, 2),
            "removed_count": original_count - filtered_count
        }
