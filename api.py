"""
API Flask pour Narrando - Gestion des Place IDs et génération de tours
Endpoints pour mobile avec options de skip pour les tests
"""
import os
import json
import time
import re
import boto3
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
from functools import wraps
from typing import Any, Dict, List, Optional

import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration

from utils.logging_config import get_logger
# Import des clients principaux
from clients.google_maps_client import GoogleMapsClient
from clients.perplexity_client import PerplexityClient
from clients.route_optimizer_client import RouteOptimizer
from clients import get_tts_client  # Factory pour TTS (OpenAI ou ElevenLabs)
from clients.openai_language_client import OpenAILanguageClient
from services.translation_service import TranslationService
from database.migrate_to_supabase import SupabaseMigrator
from admin import create_admin_blueprint
from utils.photo_url_generator import GooglePhotoURLGenerator

logger = get_logger(__name__)

def _get_timeout_seconds(env_var: str, default: float) -> float:
    """Retourne un timeout en secondes depuis l'env avec repli sécurisé."""
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


GOOGLE_PLACE_DETAILS_TIMEOUT = _get_timeout_seconds("GOOGLE_PLACE_DETAILS_TIMEOUT_SECONDS", 10.0)
GOOGLE_PHOTO_DOWNLOAD_TIMEOUT = _get_timeout_seconds("GOOGLE_PHOTO_DOWNLOAD_TIMEOUT_SECONDS", 12.0)
PERPLEXITY_TIMEOUT = _get_timeout_seconds("PERPLEXITY_TIMEOUT_SECONDS", 60.0)


def _init_sentry():
    dsn = os.getenv("SENTRY_DSN")
    if not dsn:
        logger.info("ℹ️ Sentry désactivé (SENTRY_DSN manquant)")
        return

    traces_sample_rate = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.0"))
    environment = os.getenv(
        "SENTRY_ENVIRONMENT",
        os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "development"))
    )
    send_pii = os.getenv("SENTRY_SEND_DEFAULT_PII", "false").lower() == "true"
    timeout_warning_env = os.getenv("SENTRY_TIMEOUT_WARNING", "true").lower()
    timeout_warning = timeout_warning_env not in {"0", "false", "no", "off"}

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        send_default_pii=send_pii,
        integrations=[
            FlaskIntegration(),
        ],
        traces_sample_rate=traces_sample_rate
    )

    logger.info(f"✅ Sentry initialisé (env: {environment}, traces={traces_sample_rate})")


_init_sentry()

app = Flask(__name__)
CORS(app)

# Configuration du token d'authentification
API_TOKEN = os.getenv('API_TOKEN')
if not API_TOKEN:
    logger.info("⚠️ API_TOKEN non configuré - les endpoints protégés seront désactivés")
    logger.info("   Définissez API_TOKEN pour activer l'authentification")

def require_token(f):
    """Décorateur pour vérifier le token d'authentification"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        logger.info(f"🔐 Vérification token pour endpoint: {request.endpoint}")
        
        # Si API_TOKEN n'est pas configuré, désactiver cet endpoint
        if not API_TOKEN:
            logger.info("❌ API_TOKEN non configuré")
            return jsonify({
                'error': 'Endpoint désactivé - API_TOKEN non configuré',
                'message': 'Configurez API_TOKEN dans les variables d\'environnement'
            }), 503
        
        # Vérifier le token dans les headers
        token = request.headers.get('Authorization')
        if token and token.startswith('Bearer '):
            token = token[7:]  # Enlever 'Bearer '
            logger.info(f"🔐 Token trouvé dans Authorization header")
        
        # Vérifier aussi dans le body JSON pour compatibilité
        if not token:
            data = request.get_json(silent=True)
            logger.info(f"🔐 Body JSON parsed: {data}")
            if data:
                token = data.get('token')
                if token:
                    logger.info(f"🔐 Token trouvé dans body JSON")
                else:
                    logger.info(f"🔐 Aucun token dans body JSON, clés disponibles: {list(data.keys()) if data else 'None'}")
            else:
                logger.info(f"🔐 Aucun body JSON ou parsing échoué")
        
        # Debug: afficher les premiers caractères du token
        if token:
            logger.info(f"🔐 Token reçu: {token[:10]}...{token[-10:] if len(token) > 20 else token}")
            logger.info(f"🔐 API_TOKEN configuré: {API_TOKEN[:10]}...{API_TOKEN[-10:] if len(API_TOKEN) > 20 else API_TOKEN}")
        
        # Vérifier le token
        if not token:
            logger.info("❌ Aucun token trouvé")
            # Essayer de marquer processing_city en erreur si place_id disponible
            try:
                data = request.get_json(silent=True)
                if data and data.get('place_id'):
                    from api import narrando_api
                    narrando_api.migrator.supabase.table('processing_city').update({
                        'status': 'error',
                        'error_message': 'Missing authentication token'
                    }).eq('place_id', data['place_id']).execute()
                    logger.info(f"✅ Processing city marked as error for authentication failure: {data['place_id']}")
            except Exception as auth_error:
                logger.info(f"⚠️ Could not mark processing_city as error: {auth_error}")
            return jsonify({'error': 'Token d\'authentification invalide ou manquant'}), 401
        elif token != API_TOKEN:
            logger.info("❌ Token invalide")
            # Essayer de marquer processing_city en erreur si place_id disponible
            try:
                data = request.get_json(silent=True)
                if data and data.get('place_id'):
                    from api import narrando_api
                    narrando_api.migrator.supabase.table('processing_city').update({
                        'status': 'error',
                        'error_message': 'Invalid authentication token'
                    }).eq('place_id', data['place_id']).execute()
                    logger.info(f"✅ Processing city marked as error for invalid token: {data['place_id']}")
            except Exception as auth_error:
                logger.info(f"⚠️ Could not mark processing_city as error: {auth_error}")
            return jsonify({'error': 'Token d\'authentification invalide ou manquant'}), 401
        
        logger.info("✅ Token valide")
        return f(*args, **kwargs)
    return decorated_function

# Configuration AWS S3
s3_client = None
try:
    # Configuration avec support des clés temporaires
    aws_config = {
        'aws_access_key_id': os.getenv('AWS_ACCESS_KEY_ID'),
        'aws_secret_access_key': os.getenv('AWS_SECRET_ACCESS_KEY'),
        'region_name': os.getenv('AWS_REGION', 'us-east-1')
    }
    
    # Ajouter le token de session si présent (clés temporaires)
    session_token = os.getenv('AWS_SESSION_TOKEN')
    if session_token:
        aws_config['aws_session_token'] = session_token
        
    s3_client = boto3.client('s3', **aws_config)
    S3_BUCKET = os.getenv('AWS_S3_BUCKET', 'narrando-audio-files')
    
    # Test de connexion
    s3_client.head_bucket(Bucket=S3_BUCKET)
    logger.info(f"✅ AWS S3 configuré: {S3_BUCKET}")
    
except Exception as e:
    logger.info(f"⚠️ AWS S3 non configuré: {e}")
    s3_client = None

class NarrandoAPI:
    PHOTO_MAX_PER_ATTR = int(os.getenv("PHOTO_MAX_PER_ATTR", "1"))
    PHOTO_MIRROR_WORKERS = int(os.getenv("PHOTO_MIRROR_WORKERS", "6"))

    LANGUAGE_LABELS = {
        'en': 'English',
        'fr': 'French',
        'es': 'Spanish',
        'it': 'Italian',
        'de': 'German',
        'pt': 'Portuguese'
    }

    def __init__(self):
        self.google_client = GoogleMapsClient()
        self.perplexity_client = PerplexityClient(max_workers=3, batch_size=3)
        self.route_optimizer = RouteOptimizer(max_walking_minutes=15)
        self.tts_client = get_tts_client()  # Client TTS configuré via TTS_PROVIDER (openai/elevenlabs)
        self.migrator = SupabaseMigrator()

        self.translation_languages = [
            lang.strip() for lang in os.getenv("TRANSLATION_LANGUAGES", "fr,es,it,de,pt").split(",")
            if lang.strip()
        ]
        self.language_client: Optional[OpenAILanguageClient] = None
        self.translation_service: Optional[TranslationService] = None

        try:
            self.language_client = OpenAILanguageClient()
            logger.info("✅ OpenAI Language Client initialisé")
        except Exception as e:
            logger.info(f"⚠️ OpenAI Language Client indisponible: {e}")

        if self.migrator.supabase and self.language_client:
            self.translation_service = TranslationService(
                self.migrator.supabase,
                self.language_client,
                target_languages=self.translation_languages,
            )
            logger.info(f"✅ TranslationService configuré pour langues: {self.translation_languages}")
        else:
            logger.info("⚠️ TranslationService inactif (Supabase ou OpenAI indisponible)")
    
    @staticmethod
    def _extract_narration_value(field: Any, narration_type: str, fallback: bool = False) -> Any:
        """
        Retourne la valeur associée au type de narration dans un champ JSON/textuel.
        """
        if isinstance(field, dict):
            if narration_type in field:
                return field[narration_type]
            if fallback:
                return field.get('standard')
            return None
        if isinstance(field, str):
            if narration_type == 'standard':
                return field
            return field if fallback else None
        return None

    @staticmethod
    def _merge_narration_value(field: Any, narration_type: str, value: Any) -> Dict[str, Any]:
        """
        Fusionne une valeur pour un type de narration dans un champ JSONB.
        """
        if field is None:
            merged: Dict[str, Any] = {}
        elif isinstance(field, dict):
            merged = dict(field)
        elif isinstance(field, str):
            merged = {'standard': field}
        else:
            merged = dict(field)
        
        merged[narration_type] = value
        return merged

    def _get_language_label(self, language_code: str) -> str:
        return self.LANGUAGE_LABELS.get((language_code or 'en').lower(), language_code or 'en')

    @staticmethod
    def _clean_perplexity_output(text: Optional[str]) -> Optional[str]:
        """
        Supprime les marqueurs de sources type [1], [2] et éventuels blocs Sources.
        """
        if not text:
            return text

        cleaned = re.sub(r'\[\d+\]', '', text)
        cleaned = re.sub(
            r'\n\s*(?:sources?|references?)\s*:.*$',
            '',
            cleaned,
            flags=re.IGNORECASE | re.DOTALL
        )
        cleaned = re.sub(r' {2,}', ' ', cleaned)
        return cleaned.strip()

    def _get_translation_assets(self, place_id: str, language_code: str) -> Dict[str, Any]:
        if language_code == 'en' or not self.migrator or not self.migrator.supabase:
            return {}
        try:
            attraction = self.migrator.supabase.table('attractions')\
                .select('id')\
                .eq('place_id', place_id)\
                .execute()
            if not attraction.data:
                return {}
            attraction_id = attraction.data[0]['id']
            translation = self.migrator.supabase.table('attraction_translations')\
                .select('ai_description,audio_url')\
                .eq('attraction_id', attraction_id)\
                .eq('language_code', language_code)\
                .execute()
            if not translation.data:
                return {}
            row = translation.data[0]
            assets: Dict[str, Any] = {
                'audio_url': row.get('audio_url') or {}
            }
            desc = row.get('ai_description')
            if desc:
                try:
                    assets['ai_description'] = json.loads(desc)
                except Exception:
                    assets['ai_description'] = {}
            return assets
        except Exception as e:
            logger.info(f"⚠️ Impossible de récupérer la traduction pour {place_id}/{language_code}: {e}")
            return {}

    def _normalize_attraction_names_to_english(self, attractions: List[Dict[str, Any]]):
        """
        Force les noms d'attractions fournis par Google/Perplexity à être en anglais
        pour garantir un golden record cohérent.
        """
        if not attractions or not self.language_client:
            return

        names = [attr.get('name', '') or '' for attr in attractions]
        try:
            translated = self.language_client.translate_batch(
                names,
                target_language='en',
                source_language=None  # laisse l'IA détecter la langue initiale
            )
            for attr, new_name in zip(attractions, translated):
                attr['name'] = new_name
        except Exception as error:
            logger.info(f"⚠️ Impossible de normaliser les noms en anglais: {error}")

    def _assign_tour_names(self, optimized_route: Dict[str, Any]) -> Dict[str, Any]:
        """
        Génère des noms marketing pour chaque tour (EN) si le client OpenAI est disponible.
        """
        if not self.language_client:
            logger.info("⚠️ Client de langage indisponible - noms de tours par défaut conservés.")
            return optimized_route

        tours = optimized_route.get('tours', [])
        if not tours:
            return optimized_route

        city = optimized_route.get('city', 'Unknown city')
        country = optimized_route.get('country', 'Unknown country')

        for idx, tour in enumerate(tours):
            points = tour.get('points') or []

            # Single-attraction tours keep the attraction name to avoid odd marketing titles
            if len(points) == 1:
                single_name = (points[0].get('name') or '').strip()
                if single_name:
                    tour['cluster_name'] = single_name
                    logger.info(f"✨ Tour {idx+1} renommé d'après l'attraction unique: {single_name}")
                    continue

            if not points:
                continue

            try:
                generated_name = self.language_client.generate_tour_name(city, country, points)
                if generated_name:
                    tour['cluster_name'] = generated_name
                    logger.info(f"✨ Nom marketing généré pour le tour {idx+1}: {generated_name}")
            except Exception as error:
                logger.info(f"⚠️ Impossible de générer un nom pour le tour {idx+1}: {error}")

        return optimized_route
        
    def get_city_from_place_id(self, place_id: str) -> Dict:
        """Récupère les informations d'une ville à partir de son Place ID Google"""
        try:
            # Utiliser l'API Place Details de Google
            details_url = f"https://maps.googleapis.com/maps/api/place/details/json"
            params = {
                'place_id': place_id,
                'fields': 'name,formatted_address,address_components,geometry',
                'language': 'en',
                'key': os.getenv('GOOGLE_PLACES_API_KEY')
            }
            
            response = requests.get(details_url, params=params, timeout=GOOGLE_PLACE_DETAILS_TIMEOUT)
            data = response.json()
            
            if data['status'] != 'OK':
                raise Exception(f"API Google error: {data['status']}")
                
            result = data['result']
            
            # Extraire ville et pays depuis les composants d'adresse
            city = None
            country = None
            country_iso = None
            
            for component in result.get('address_components', []):
                types = component['types']
                if not city and ('locality' in types or 'postal_town' in types):
                    city = component['long_name']
                if 'country' in types:
                    country = component['long_name']
                    country_iso = component['short_name']
            
            if not city:
                # Pas de localité => arrêter le traitement pour éviter d'utiliser une région
                component_types = [
                    component['types']
                    for component in result.get('address_components', [])
                ]
                error_msg = (
                    f"Aucune localité trouvée pour place_id {place_id}. "
                    f"Types disponibles: {component_types}"
                )
                if self.migrator and self.migrator.supabase:
                    try:
                        self.migrator.supabase.table('processing_city').update({
                            'status': 'error',
                            'error_message': error_msg,
                            'current_step_key': 'error_city_lookup',
                            'progress_percent': 100
                        }).eq('place_id', place_id).execute()
                        logger.info(f"✅ processing_city mis en erreur (localité manquante) pour {place_id}")
                    except Exception as mark_error:
                        logger.info(f"⚠️ Impossible de marquer processing_city pour {place_id}: {mark_error}")
                raise Exception(error_msg)
                
            return {
                'place_id': place_id,
                'city': city,
                'country': country,
                'country_iso': country_iso,
                'formatted_address': result['formatted_address'],
                'location': result['geometry']['location']
            }
            
        except requests.Timeout as timeout_err:
            if self.migrator and self.migrator.supabase:
                try:
                    self.migrator.supabase.table('processing_city').update({
                        'status': 'error',
                        'error_message': f"Timeout during city generation: {timeout_err}",
                        'current_step_key': 'timeout',
                        'progress_percent': 100
                    }).eq('place_id', place_id).execute()
                except Exception:
                    pass
            raise Exception(f"Timeout during city generation: {timeout_err}")
        except Exception as e:
            if self.migrator and self.migrator.supabase:
                try:
                    self.migrator.supabase.table('processing_city').update({
                        'status': 'error',
                        'error_message': str(e),
                        'current_step_key': 'error_city_lookup',
                        'progress_percent': 100
                    }).eq('place_id', place_id).execute()
                    logger.info(f"✅ processing_city mis en erreur pour {place_id}")
                except Exception as mark_error:
                    logger.info(f"⚠️ Impossible de marquer processing_city pour {place_id}: {mark_error}")
            raise Exception(f"Erreur lors de la récupération de la ville: {str(e)}")

    def generate_tour_from_place_id(self, place_id: str, skip_audio: bool = False, 
                                   skip_descriptions: bool = False) -> Dict:
        """Génère un tour complet à partir d'un Place ID avec options de skip"""
        try:
            # Helper pour mettre à jour la progression
            def update_progress(progress_percent: int, step_key: str, description: str, status: Optional[str] = None):
                """Met à jour la progression de génération de la ville dans processing_city."""
                if self.migrator and self.migrator.supabase:
                    payload = {
                        'progress_percent': progress_percent,
                        'current_step_key': step_key
                    }
                    if status:
                        payload['status'] = status
                    try:
                        self.migrator.supabase.table('processing_city').update(payload).eq('place_id', place_id).execute()
                        logger.info(f"📈 Progress {progress_percent}% ({step_key}): {description}")
                    except Exception as e:
                        logger.info(f"⚠️ Failed to update progress: {e}")

            # Étape 1: Récupérer les infos de la ville
            update_progress(10, "fetch_city_details", "Récupération des informations de la ville...")
            logger.info(f"🔍 Récupération des infos pour place_id: {place_id}")
            city_info = self.get_city_from_place_id(place_id)
            
            city = city_info['city']
            country = city_info['country']
            
            logger.info(f"✅ Ville trouvée: {city}, {country}")
            
            # Étape 2: Recherche des attractions
            update_progress(30, "search_attractions", "Recherche des attractions populaires...")
            logger.info(f"🔍 Recherche des attractions...")
            attractions = self.google_client.search_tourist_attractions(
                city=city, 
                country=country, 
                max_results=30
            )
            logger.info(f"✅ {len(attractions)} attractions trouvées")
            
            # Étape 3: Filtrage V2 parallèle
            update_progress(50, "filter_attractions", "Analyse et sélection des meilleurs lieux...")
            logger.info(f"🧠 Filtrage des attractions...")
            filtered_attractions = self.perplexity_client.filter_attractions(
                attractions=attractions,
                city=city,
                country=country
            )
            logger.info(f"✅ {len(filtered_attractions)} attractions conservées")

            # Garantir que tous les noms sont en anglais (golden record)
            self._normalize_attraction_names_to_english(filtered_attractions)

            # Mirror photos to S3 (in-memory) before migration
            filtered_attractions = self._mirror_photos_to_s3(
                filtered_attractions,
                max_photos=self.PHOTO_MAX_PER_ATTR,
                workers=self.PHOTO_MIRROR_WORKERS,
            )
            
            # Étape 4: Optimisation de l'itinéraire
            update_progress(70, "optimize_route", "Optimisation des itinéraires de visite...")
            logger.info(f"🗺️ Optimisation de l'itinéraire...")
            optimized_route = self.route_optimizer.optimize_route(filtered_attractions)
            
            # Ajouter les infos de la ville
            optimized_route.update({
                'place_id': place_id,
                'city': city,
                'country': country,
                'country_iso': city_info['country_iso'],
                'formatted_address': city_info['formatted_address'],
                'version': 'API_V1',
                'created_at': time.time(),
                'skip_audio': skip_audio,
                'skip_descriptions': skip_descriptions
            })

            # Générer des noms marketing pour les tours (EN)
            optimized_route = self._assign_tour_names(optimized_route)
            
            # Étape 5: Migration vers Supabase avec données directes
            update_progress(90, "save_to_supabase", "Sauvegarde et finalisation...")
            logger.info(f"💾 Sauvegarde en base...")
            
            # Migrer vers Supabase avec les attractions filtrées directement (avec photos)
            migration_result = self.migrator.migrate_route_data_with_source_attractions(
                optimized_route, 
                filtered_attractions
            )
                
            if not migration_result or not migration_result.get('success'):
                logger.info("⚠️ Erreur lors de la migration Supabase")
                error_msg = migration_result.get('error', 'Erreur inconnue') if migration_result else 'Migration échec'
                optimized_route['migration_error'] = error_msg
            else:
                logger.info(f"✅ Tours sauvés: {migration_result['tours_count']} tours, {migration_result['attractions_count']} attractions")
                if self.translation_service and migration_result.get('success'):
                    self.translation_service.translate_city_assets(
                        migration_result.get('city_id'),
                        migration_result.get('tour_ids', [])
                    )
                
            # Ajouter les informations de migration au résultat
            optimized_route.update({
                'city_id': migration_result.get('city_id') if migration_result else None,
                'tour_ids': migration_result.get('tour_ids', []) if migration_result else [],
                'tours_count': migration_result.get('tours_count', 0) if migration_result else 0,
                'migration_success': migration_result.get('success', False) if migration_result else False
            })
            
            update_progress(100, "complete", "Génération terminée !", status='completed')
            return optimized_route
            
        except Exception as e:
            if self.migrator and self.migrator.supabase:
                try:
                    self.migrator.supabase.table('processing_city').update({
                        'status': 'error',
                        'error_message': str(e),
                        'current_step_key': 'error',
                        'progress_percent': 100
                    }).eq('place_id', place_id).execute()
                except:
                    pass
            raise Exception(f"Erreur génération tour: {str(e)}")

    def _mirror_photos_to_s3(
        self,
        attractions: List[Dict[str, Any]],
        max_photos: int = 1,
        workers: int = 4,
    ) -> List[Dict[str, Any]]:
        """
        Télécharge les photos existantes ou Google, pousse sur S3, remplace photos par URLs S3.
        """
        if not s3_client or not S3_BUCKET:
            logger.info("S3 non configuré pour les photos, on conserve les URLs existantes.")
            return attractions

        try:
            photo_generator = GooglePhotoURLGenerator()
            # Forcer la clé si fournie par env
            google_key = photo_generator.google_api_key
        except Exception as exc:
            logger.info("GooglePhotoURLGenerator indisponible: %s", exc)
            return attractions

        max_photos = max(1, int(max_photos))
        workers = max(1, int(workers))

        results: List[Optional[Dict[str, Any]]] = [None] * len(attractions)

        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_idx = {
                executor.submit(
                    self._mirror_single_attraction_photos,
                    attraction,
                    photo_generator,
                    max_photos,
                ): idx
                for idx, attraction in enumerate(attractions)
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                except Exception as exc:
                    logger.warning("Mirror photos failed for attraction index %s: %s", idx, exc)
                    results[idx] = attractions[idx]

        return [r for r in results if r is not None]

    def _mirror_single_attraction_photos(
        self,
        attraction: Dict[str, Any],
        photo_generator: GooglePhotoURLGenerator,
        max_photos: int,
    ) -> Dict[str, Any]:
        place_id = attraction.get("place_id")
        photos = attraction.get("photos") or []
        name = attraction.get("name", "Unknown")

        if not place_id:
            return attraction

        candidates: List[Tuple[Dict[str, Any], str]] = []

        for photo in photos:
            if len(candidates) >= max_photos:
                break
            if not isinstance(photo, dict):
                continue
            url = photo.get("photo_url") or photo.get("url")
            if not url:
                ref = photo.get("photo_reference")
                if ref:
                    try:
                        url = photo_generator.generate_photo_url(ref, max_width=800, max_height=800)
                    except Exception:
                        url = None
            if url:
                candidates.append((photo, url))

        if len(candidates) < max_photos:
            needed = max_photos - len(candidates)
            fetched = self._fetch_google_photos(photo_generator, place_id, needed)
            for ph in fetched:
                url = ph.get("photo_url")
                if url:
                    candidates.append((ph, url))
                if len(candidates) >= max_photos:
                    break

        if not candidates:
            logger.info("Aucune photo utilisable pour %s (%s)", name, place_id)
            return attraction

        uploaded: List[Dict[str, Any]] = []
        for idx, (photo, url) in enumerate(candidates[:max_photos]):
            content = self._download_photo(url)
            if not content:
                continue
            key = f"images/attractions/{place_id}/{idx+1}_{int(time.time())}.jpg"
            s3_client.put_object(
                Bucket=S3_BUCKET,
                Key=key,
                Body=content,
                ContentType="image/jpeg",
            )
            uploaded_photo = dict(photo)
            uploaded_photo["photo_url"] = f"https://{S3_BUCKET}.s3.amazonaws.com/{key}"
            uploaded_photo["s3_key"] = key
            uploaded_photo["storage"] = "s3"
            uploaded.append(uploaded_photo)

        if not uploaded:
            return attraction

        updated_attraction = dict(attraction)
        updated_attraction["photos"] = uploaded
        return updated_attraction

    def _fetch_google_photos(
        self,
        photo_generator: GooglePhotoURLGenerator,
        place_id: str,
        max_results: int,
    ) -> List[Dict[str, Any]]:
        details_url = "https://maps.googleapis.com/maps/api/place/details/json"
        params = {"place_id": place_id, "fields": "photo", "key": photo_generator.google_api_key}
        try:
            resp = requests.get(details_url, params=params, timeout=GOOGLE_PLACE_DETAILS_TIMEOUT)
            if resp.status_code != 200:
                logger.warning("Place Details %s a renvoyé %s", place_id, resp.status_code)
                return []
            data = resp.json()
            photos = data.get("result", {}).get("photos", []) or []
            formatted: List[Dict[str, Any]] = []
            for photo in photos:
                ref = photo.get("photo_reference")
                if not ref:
                    continue
                try:
                    url = photo_generator.generate_photo_url(ref, max_width=800, max_height=800)
                except Exception:
                    url = None
                entry = {
                    "photo_reference": ref,
                    "width": photo.get("width"),
                    "height": photo.get("height"),
                    "html_attributions": photo.get("html_attributions"),
                }
                if url:
                    entry["photo_url"] = url
                formatted.append(entry)
                if len(formatted) >= max_results:
                    break
            return formatted
        except Exception as exc:
            logger.warning("Erreur Place Details %s: %s", place_id, exc)
            return []

    @staticmethod
    def _download_photo(url: str) -> Optional[bytes]:
        try:
            resp = requests.get(url, timeout=GOOGLE_PHOTO_DOWNLOAD_TIMEOUT)
            if resp.status_code == 200:
                return resp.content
        except requests.RequestException:
            return None
        return None

    def generate_preview_audio(
        self,
        tour_id: str,
        attraction_index: int = 0,
        force_regenerate: bool = False,
        narration_type: str = "standard",
        language_code: str = "en"
    ) -> Dict:
        """Génère l'audio de prévisualisation pour le premier point d'intérêt d'un tour spécifique"""
        try:
            # Récupérer les données du tour spécifique depuis Supabase
            logger.info(f"🔍 Récupération tour_id: {tour_id}")
            tour_data = self.migrator.get_specific_tour_by_id(tour_id)
            
            if not tour_data:
                raise Exception(f"Tour avec ID {tour_id} non trouvé")
            
            logger.info(f"🔍 Tour trouvé: {tour_data.get('tour', {}).get('name', 'Unknown')}")
            
            if not tour_data.get('tour', {}).get('attractions'):
                raise Exception("Tour trouvé mais aucune attraction")
            
            # Prendre l'attraction à l'index demandé (par défaut 0 = première)
            attractions = tour_data['tour']['attractions']
            logger.info(f"🔍 Nombre d'attractions dans le tour: {len(attractions)}")
            self._ensure_walking_paths_ready(tour_id, attractions)
            
            if attraction_index >= len(attractions):
                raise Exception(f"Index {attraction_index} invalide, tour a {len(attractions)} attractions")
                
            target_attraction = attractions[attraction_index]
            logger.info(f"🔍 Attraction sélectionnée à l'index {attraction_index}: {target_attraction.get('name', 'None') if target_attraction else 'NULL'}")
            
            # Vérifier que l'attraction existe bien
            if not target_attraction:
                raise Exception(f"Attraction à l'index {attraction_index} est None")
            
            if not target_attraction.get('place_id'):
                logger.info(f"🔍 DEBUG - Attraction complète: {json.dumps(target_attraction, indent=2, ensure_ascii=False)}")
                raise Exception(f"Attraction sans place_id: {target_attraction.get('name', 'Unknown')}")
            
            # Vérifier si audio déjà généré (même logique que le tour complet)
            translation_assets = self._get_translation_assets(target_attraction['place_id'], language_code)
            audio_source = translation_assets.get('audio_url') if language_code != 'en' else target_attraction.get('audio_url')
            existing_audio = self._extract_narration_value(audio_source, narration_type)
            if existing_audio and not force_regenerate:
                logger.info(f"⏭️ Audio ({narration_type}) déjà existant pour {target_attraction['name']}")
                return {
                    'tour_info': {
                        'id': tour_data['tour']['id'],
                        'name': tour_data['tour']['name'], 
                        'total_attractions': len(attractions)
                    },
                    'attraction': target_attraction,
                    'attraction_index': attraction_index,
                    'audio_url': existing_audio,
                    'description': self._extract_narration_value(target_attraction.get('ai_description'), narration_type),
                    'narration_type': narration_type,
                    'language_code': language_code,
                    'message': 'Audio existant réutilisé'
                }
            
            # Générer la description si nécessaire
            desc_source = translation_assets.get('ai_description') if language_code != 'en' else target_attraction.get('ai_description')
            description = self._extract_narration_value(desc_source, narration_type)
            if not description or force_regenerate:
                logger.info(f"🧠 Génération description ({narration_type}) pour: {target_attraction.get('name', 'Unknown')}")
                description = self.generate_attraction_description(target_attraction, narration_type, language_code)
                
                if not description:
                    raise Exception(f"Description non générée pour {target_attraction['name']}")
                
                if language_code == 'en':
                    target_attraction['ai_description'] = self._merge_narration_value(
                        target_attraction.get('ai_description'),
                        narration_type,
                        description
                    )
                self.migrator.update_attraction_description(
                    target_attraction['place_id'], 
                    description,
                    narration_type,
                    language_code
                )
            
            # Récupérer city_id pour la structure des dossiers
            city_id = tour_data['city']['id']
            
            # Générer l'audio avec la nouvelle structure (même nom que génération complète)
            # Format: {point_order}_{attraction_uuid}
            point_order = target_attraction.get('point_order', attraction_index + 1)
            attraction_uuid = target_attraction.get('id', str(attraction_index))
            filename = f"{point_order}_{attraction_uuid}_{language_code}_{narration_type}"
            
            logger.info(f"🎵 Génération audio preview pour: {target_attraction['name']}")
            audio_url = self.generate_audio_from_description(
                description,
                filename,
                city_id,
                tour_id,
                "attraction",
                narration_type,
                language_code
            )
            
            # Mettre à jour l'URL audio en base
            self.migrator.update_attraction_audio_url(
                target_attraction['place_id'], 
                audio_url,
                narration_type,
                language_code
            )
            if language_code == 'en':
                target_attraction['audio_url'] = self._merge_narration_value(
                    target_attraction.get('audio_url'),
                    narration_type,
                    audio_url
                )
            
            return {
                'tour_info': {
                    'id': tour_data['tour']['id'],
                    'name': tour_data['tour']['name'], 
                    'total_attractions': len(attractions)
                },
                'attraction': target_attraction,
                'attraction_index': attraction_index,
                'audio_url': audio_url,
                'description': description,
                'narration_type': narration_type,
                'language_code': language_code
            }
            
        except Exception as e:
            raise Exception(f"Erreur génération preview: {str(e)}")

    def generate_complete_tour_audio(
        self,
        tour_id: str,
        force_regenerate: bool = False,
        narration_type: str = "standard",
        language_code: str = "en"
    ) -> Dict:
        """Génère tous les audios d'un tour spécifique"""
        try:
            # Récupérer les données du tour spécifique
            tour_data = self.migrator.get_specific_tour_by_id(tour_id)
            
            if not tour_data:
                raise Exception(f"Tour avec ID {tour_id} non trouvé")
            
            if not tour_data.get('tour', {}).get('attractions'):
                raise Exception("Tour trouvé mais aucune attraction")
            
            language_code = (language_code or 'en').lower()
            language_label = self._get_language_label(language_code)
            results = []
            attractions = tour_data['tour']['attractions']
            tour_name = tour_data['tour']['name']
            city_id = tour_data['city']['id']
            self._ensure_walking_paths_ready(tour_id, attractions)
            
            total_attractions = len(attractions)
            logger.info(
                f"🎵 Génération audio pour {total_attractions} attractions du tour: {tour_name} "
                f"(langue: {language_label} [{language_code}])"
            )

            for attr_idx, attraction in enumerate(attractions):
                # Update progress
                if total_attractions <= 1:
                    progress_percent = 50  # afficher une progression visible même pour 1 seul POI
                else:
                    progress_percent = min(
                        95,
                        int(((attr_idx + 1) / total_attractions) * 90) + 5
                    )
                if self.migrator and self.migrator.supabase:
                    try:
                        self.migrator.supabase.table('processing_tour_generation').update({
                            'progress_percent': progress_percent,
                            'current_step_key': f"attraction_{attr_idx + 1}_of_{total_attractions}"
                        }).eq('tour_id', tour_id).eq('narration_type', narration_type).eq('language_code', language_code).execute()
                    except Exception as e:
                        logger.info(f"⚠️ Failed to update audio progress: {e}")

                translation_assets = self._get_translation_assets(attraction['place_id'], language_code)
                
                # Vérifier si audio déjà généré
                audio_source = translation_assets.get('audio_url') if language_code != 'en' else attraction.get('audio_url')
                existing_audio = self._extract_narration_value(audio_source, narration_type)
                if existing_audio and not force_regenerate:
                    logger.info(f"⏭️ Audio ({narration_type}) déjà existant pour {attraction['name']}")
                    continue
                
                # Générer la description si nécessaire
                desc_source = translation_assets.get('ai_description') if language_code != 'en' else attraction.get('ai_description')
                description = self._extract_narration_value(desc_source, narration_type)
                if not description or force_regenerate:
                    description = self.generate_attraction_description(attraction, narration_type, language_code)
                    
                    if not description:
                        raise Exception(f"Description non générée pour {attraction['name']}")
                    
                    self.migrator.update_attraction_description(
                        attraction['place_id'], 
                        description,
                        narration_type,
                        language_code
                    )
                    if language_code == 'en':
                        attraction['ai_description'] = self._merge_narration_value(
                            attraction.get('ai_description'),
                            narration_type,
                            description
                        )
                
                # Générer l'audio avec la nouvelle structure
                # Format: {point_order}_{attraction_uuid}
                point_order = attraction.get('point_order', attr_idx + 1)
                attraction_uuid = attraction.get('id', str(attr_idx))
                filename = f"{point_order}_{attraction_uuid}_{language_code}_{narration_type}"
                
                audio_url = self.generate_audio_from_description(
                    description,
                    filename,
                    city_id,
                    tour_id,
                    "attraction",
                    narration_type,
                    language_code
                )
                
                # Mettre à jour en base
                self.migrator.update_attraction_audio_url(
                    attraction['place_id'], 
                    audio_url,
                    narration_type,
                    language_code
                )
                if language_code == 'en':
                    attraction['audio_url'] = self._merge_narration_value(
                        attraction.get('audio_url'),
                        narration_type,
                        audio_url
                    )
                
                results.append({
                    'attraction_name': attraction['name'],
                    'place_id': attraction['place_id'],
                    'audio_url': audio_url,
                    'attraction_index': attr_idx,
                    'point_order': attraction.get('point_order', attr_idx + 1),
                    'narration_type': narration_type,
                    'language_code': language_code
                })
            
            # Final update
            if self.migrator and self.migrator.supabase:
                try:
                    self.migrator.supabase.table('processing_tour_generation').update({
                        'progress_percent': 100,
                        'current_step_key': 'complete',
                        'status': 'completed'
                    }).eq('tour_id', tour_id).eq('narration_type', narration_type).eq('language_code', language_code).execute()
                except Exception as e:
                    logger.info(f"⚠️ Failed to update final audio progress: {e}")

            return {
                'tour_id': tour_id,
                'tour_name': tour_name,
                'generated_audios': results,
                'total_generated': len(results),
                'total_attractions': len(attractions),
                'narration_type': narration_type,
                'language_code': language_code
            }
            
        except Exception as e:
            if self.migrator and self.migrator.supabase:
                try:
                    self.migrator.supabase.table('processing_tour_generation').update({
                        'status': 'error',
                        'error_message': str(e),
                        'current_step_key': 'error',
                        'progress_percent': 100
                    }).eq('tour_id', tour_id).eq('narration_type', narration_type).eq('language_code', language_code).execute()
                except:
                    pass
            raise Exception(f"Erreur génération tour complet: {str(e)}")

    def generate_complete_user_tour_audio(
        self,
        user_tour_id: str,
        force_regenerate: bool = False,
        narration_type: str = "standard",
        language_code: str = "en"
    ) -> Dict:
        """Génère tous les audios d'un tour custom (user_tours)"""
        try:
            tour_data = self.migrator.get_specific_user_tour_by_id(user_tour_id)

            if not tour_data:
                raise Exception(f"Tour custom avec ID {user_tour_id} non trouvé")

            if not tour_data.get('tour', {}).get('attractions'):
                raise Exception("Tour custom trouvé mais aucune attraction")

            language_code = (language_code or 'en').lower()
            language_label = self._get_language_label(language_code)
            results = []
            attractions = tour_data['tour']['attractions']
            tour_name = tour_data['tour']['name']
            city_id = tour_data.get('city', {}).get('id') if tour_data.get('city') else None

            if not city_id:
                raise Exception("City_id manquant pour le tour custom")

            total_attractions = len(attractions)
            logger.info(
                f"🎵 Génération audio (custom) pour {total_attractions} attractions du tour: {tour_name} "
                f"(langue: {language_label} [{language_code}])"
            )

            # Assurer les walking paths custom avant génération
            self._ensure_user_walking_paths_ready(user_tour_id, attractions)

            for attr_idx, attraction in enumerate(attractions):
                if total_attractions <= 1:
                    progress_percent = 50
                else:
                    progress_percent = min(
                        95,
                        int(((attr_idx + 1) / total_attractions) * 90) + 5
                    )

                if self.migrator and self.migrator.supabase:
                    try:
                        self.migrator.supabase.table('processing_user_tour_generation').update({
                            'progress_percent': progress_percent
                        }).eq('user_tour_id', user_tour_id).eq('narration_type', narration_type).eq('language_code', language_code).execute()
                    except Exception as e:
                        logger.info(f"⚠️ Failed to update custom audio progress: {e}")

                translation_assets = self._get_translation_assets(attraction['place_id'], language_code)

                audio_source = translation_assets.get('audio_url') if language_code != 'en' else attraction.get('audio_url')
                existing_audio = self._extract_narration_value(audio_source, narration_type)
                if existing_audio and not force_regenerate:
                    logger.info(f"⏭️ Audio ({narration_type}) déjà existant pour {attraction['name']} (custom)")
                    continue

                desc_source = translation_assets.get('ai_description') if language_code != 'en' else attraction.get('ai_description')
                description = self._extract_narration_value(desc_source, narration_type)
                if not description or force_regenerate:
                    description = self.generate_attraction_description(attraction, narration_type, language_code)

                    if not description:
                        raise Exception(f"Description non générée pour {attraction['name']}")

                    self.migrator.update_attraction_description(
                        attraction['place_id'],
                        description,
                        narration_type,
                        language_code
                    )
                    if language_code == 'en':
                        attraction['ai_description'] = self._merge_narration_value(
                            attraction.get('ai_description'),
                            narration_type,
                            description
                        )

                point_order = attraction.get('point_order', attr_idx + 1)
                attraction_uuid = attraction.get('id', str(attr_idx))
                filename = f"{point_order}_{attraction_uuid}_{language_code}_{narration_type}"

                audio_url = self.generate_audio_from_description(
                    description,
                    filename,
                    city_id,
                    user_tour_id,
                    "attraction",
                    narration_type,
                    language_code
                )

                self.migrator.update_attraction_audio_url(
                    attraction['place_id'],
                    audio_url,
                    narration_type,
                    language_code
                )
                if language_code == 'en':
                    attraction['audio_url'] = self._merge_narration_value(
                        attraction.get('audio_url'),
                        narration_type,
                        audio_url
                    )

                results.append({
                    'attraction_name': attraction['name'],
                    'place_id': attraction['place_id'],
                    'audio_url': audio_url,
                    'attraction_index': attr_idx,
                    'point_order': point_order,
                    'narration_type': narration_type,
                    'language_code': language_code
                })

            if self.migrator and self.migrator.supabase:
                try:
                    self.migrator.supabase.table('processing_user_tour_generation').update({
                        'progress_percent': 100,
                        'status': 'ready'
                    }).eq('user_tour_id', user_tour_id).eq('narration_type', narration_type).eq('language_code', language_code).execute()
                except Exception as e:
                    logger.info(f"⚠️ Failed to update final custom audio progress: {e}")

            return {
                'user_tour_id': user_tour_id,
                'tour_name': tour_name,
                'generated_audios': results,
                'total_generated': len(results),
                'total_attractions': len(attractions),
                'narration_type': narration_type,
                'language_code': language_code
            }

        except Exception as e:
            if self.migrator and self.migrator.supabase:
                try:
                    self.migrator.supabase.table('processing_user_tour_generation').update({
                        'status': 'error',
                        'progress_percent': 100
                    }).eq('user_tour_id', user_tour_id).eq('narration_type', narration_type).eq('language_code', language_code).execute()
                except:
                    pass
            raise Exception(f"Erreur génération tour custom: {str(e)}")

    def _ensure_walking_paths_ready(self, tour_id: str, attractions: List[Dict[str, Any]]):
        """
        Génère les walking_paths pour un tour si nécessaire (calcul effectué à la demande).
        """
        if not self.migrator or not self.migrator.supabase:
            raise ValueError("Supabase indisponible pour générer les walking_paths")
        if not self.route_optimizer:
            raise ValueError("RouteOptimizer non initialisé")

        self.migrator.ensure_walking_paths_for_tour(
            tour_id,
            attractions,
            self.route_optimizer.generate_walking_path
        )

    def _ensure_user_walking_paths_ready(self, user_tour_id: str, attractions: List[Dict[str, Any]]):
        """
        Génère les walking_paths pour un tour custom si nécessaire (calcul à la demande).
        """
        if not self.migrator or not self.migrator.supabase:
            raise ValueError("Supabase indisponible pour générer les walking_paths custom")
        if not self.route_optimizer:
            raise ValueError("RouteOptimizer non initialisé")

        self.migrator.ensure_user_walking_paths_for_tour(
            user_tour_id,
            attractions,
            self.route_optimizer.generate_walking_path
        )

    def generate_attraction_description(
        self,
        attraction: Dict,
        narration_type: str = "standard",
        language_code: str = "en"
    ) -> Optional[str]:
        """Génère une description détaillée pour une attraction"""
        try:
            narration_guidelines = {
                "standard": "- Ton narratif immersif pour un public adulte\n- Niveau de détail équilibré\n- Style enthousiaste et chaleureux",
                "child": "- Utilise un vocabulaire simple et imagé\n- Ajoute des anecdotes amusantes\n- Ton joyeux et pédagogique adapté aux enfants de 8-12 ans",
                "expert": "- Approche plus technique et historique\n- Intègre des faits précis et des chiffres clés\n- Ton sérieux et érudit pour un public passionné"
            }
            style_instruction = narration_guidelines.get(narration_type, narration_guidelines["standard"])
            language_label = self._get_language_label(language_code)
            
            # Utiliser Perplexity pour générer une description riche
            prompt = f"""
You are an expert travel narrator. Create a {language_label} audio script (300-400 words) for the following attraction:

Name: {attraction['name']}
Address: {attraction.get('formatted_address', '')}
Types: {attraction.get('types', [])}
Rating: {attraction.get('rating', 'N/A')}/5

The script must be:
- Engaging, immersive, and rich in historical/cultural anecdotes
- Suitable for an audio guide
- Written entirely in {language_label}
- Matching this narration style: {narration_type}

Specific guidelines:
{style_instruction}

Output format (strict):
- Only the narration text, without any preamble, apology, or explanation.
- No sentences like "voici", "en français", or "voici la description". Jump straight into the narration.
            """
            
            # Appel à l'API Perplexity
            response = requests.post(
                'https://api.perplexity.ai/chat/completions',
                headers={
                    'Authorization': f'Bearer {os.getenv("PERPLEXITY_API_KEY")}',
                    'Content-Type': 'application/json'
                },
                json={
                    'model': 'sonar',
                    'messages': [{'role': 'user', 'content': prompt}],
                    'max_tokens': 1000
                },
                timeout=PERPLEXITY_TIMEOUT
            )
            
            if response.status_code == 200:
                description = response.json()['choices'][0]['message']['content']
                return self._clean_perplexity_output(description)
            else:
                raise Exception(f"API Perplexity error: {response.status_code}")
                
        except Exception as e:
            logger.info(f"⚠️ Erreur génération description: {e}")
            logger.info(f"🔍 Données attraction reçues: {attraction}")
            return None

    def generate_audio_from_description(
        self,
        description: str,
        filename: str,
        city_id: str,
        tour_id: str,
        content_type: str = "attraction",
        narration_type: str = "standard",
        language_code: str = "en"
    ) -> str:
        """
        Génère un fichier audio à partir d'une description avec style narratif optimisé
        
        Args:
            description: Texte de la description
            filename: Nom du fichier de sortie
            city_id: UUID de la ville pour structurer les dossiers
            tour_id: UUID du tour pour structurer les dossiers
            content_type: Type de contenu ('attraction', 'history', 'anecdote', 'practical')
            narration_type: Variante de narration (standard, child, expert, ...)
        """
        try:
            # Vérifier si le client TTS est disponible
            if not self.tts_client.client:
                raise Exception("Client TTS non configuré ou non disponible")

            language_label = self._get_language_label(language_code)

            # Génération audio avec style narratif optimisé
            logger.info(
                f"🎵 Génération audio guide touristique (type: {content_type}, narration: {narration_type}, "
                f"langue: {language_label} [{language_code}])..."
            )
            voice_id = self.tts_client.get_voice_id(language_code)
            audio_data = self.tts_client.generate_tourist_guide_audio(
                description,
                content_type,
                voice_id=voice_id,
                language_label=language_label
            )
            
            # Sauvegarder sur S3 avec nouvelle structure hiérarchique
            timestamp = int(time.time())
            audio_key = f"audio/{city_id}/{tour_id}/{filename}_{timestamp}.mp3"
            
            # S3 OBLIGATOIRE - Aucun fallback
            if not s3_client:
                raise Exception("S3 non configuré ")
            
            # Upload vers S3 (obligatoire)
            s3_client.put_object(
                Bucket=S3_BUCKET,
                Key=audio_key,
                Body=audio_data,
                ContentType='audio/mpeg'
            )
            
            audio_url = f"https://{S3_BUCKET}.s3.amazonaws.com/{audio_key}"
            logger.info(f"✅ Audio stocké S3: {audio_url}")
            
            # En mode DEV: aussi sauver en local pour vérification
            if os.getenv('DEV_MODE') == 'true':
                local_path = f"data/audio/{city_id}/{tour_id}/{filename}_{timestamp}.mp3"
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                
                with open(local_path, 'wb') as f:
                    f.write(audio_data)
                
                logger.info(f"🔧 DEV: Copie locale pour vérification: {local_path}")
            
            # Toujours retourner l'URL S3
            return audio_url
                
        except Exception as e:
            raise Exception(f"Erreur génération audio SDK: {str(e)}")

# Instance globale
narrando_api = NarrandoAPI()

# Enregistrer le blueprint admin (UI + API)
try:
    admin_blueprint = create_admin_blueprint(narrando_api)
    app.register_blueprint(admin_blueprint)
    logger.info("✅ Blueprint admin chargé (/admin)")
except Exception as admin_error:
    logger.info(f"⚠️ Impossible de charger le blueprint admin: {admin_error}")

def _cleanup_preview_processing_record(tour_id: str) -> None:
    """Supprime l'entrée processing_tour_preview pour débloquer Flutter."""
    if narrando_api.migrator and narrando_api.migrator.supabase:
        try:
            narrando_api.migrator.supabase.table('processing_tour_preview') \
                .delete() \
                .eq('tour_id', tour_id) \
                .execute()
            logger.info(f"✅ processing_tour_preview cleaned for tour_id: {tour_id}")
        except Exception as cleanup_error:
            logger.info(f"⚠️ Erreur suppression processing_tour_preview: {cleanup_error}")

def _mark_preview_processing_error(tour_id: str, error_message: str) -> None:
    """Marque l'entrée processing_tour_preview en erreur pour propagation mobile."""
    if narrando_api.migrator and narrando_api.migrator.supabase:
        try:
            narrando_api.migrator.supabase.table('processing_tour_preview') \
                .update({
                    'status': 'error'
                }) \
                .eq('tour_id', tour_id) \
                .execute()
            logger.info(f"✅ processing_tour_preview marked as error for tour_id: {tour_id} ({error_message})")
        except Exception as mark_error:
            logger.info(f"⚠️ Impossible de marquer processing_tour_preview en erreur: {mark_error}")

# Routes API
@app.route('/', methods=['GET'])
def root():
    """Route racine de l'API"""
    return jsonify({
        'service': 'Narrando API',
        'version': 'V2 (VPS)',
        'status': 'running'
    })

@app.route('/health', methods=['GET'])
def health_check():
    """Vérification de santé de l'API"""
    from datetime import datetime
    return jsonify({
        'status': 'healthy',
        'version': 'V2',
        'timestamp': time.time(),
        'datetime': datetime.now().isoformat(),
        'utc_datetime': datetime.utcnow().isoformat() + 'Z'
    })

@app.route('/generate-city-data', methods=['POST'])
@require_token
def generate_city_data():
    """
    Génère les données d'une ville (attractions + tours) à partir d'un Place ID Google
    Body: {
        "place_id": "ChIJD7fiBh9u5kcRYJSMaMOCCwQ",
        "skip_audio": false,
        "skip_descriptions": false
    }
    """
    logger.info(f"🚀 ENDPOINT /generate-city-data appelé")
    logger.info(f"📥 Headers reçus: {dict(request.headers)}")
    
    try:
        data = request.get_json()
        logger.info(f"📥 Payload reçu: {data}")
        
        place_id = data.get('place_id') if data else None
        skip_audio = data.get('skip_audio', False) if data else False
        skip_descriptions = data.get('skip_descriptions', False) if data else False
        
        if not place_id:
            return jsonify({'error': 'place_id requis'}), 400
        
        logger.info(f"🚀 Génération tour pour place_id: {place_id}")
        logger.info(f"   Skip audio: {skip_audio}")
        logger.info(f"   Skip descriptions: {skip_descriptions}")
        
        tour_data = narrando_api.generate_tour_from_place_id(
            place_id, skip_audio, skip_descriptions
        )
        
        # 🔧 CRITIQUE: Nettoyer la table processing_city pour débloquer l'app mobile
        try:
            narrando_api.migrator.supabase.table('processing_city') \
                .delete() \
                .eq('place_id', place_id) \
                .neq('status', 'error') \
                .execute()
            logger.info(f"✅ Processing city cleaned for place_id: {place_id}")
        except Exception as cleanup_error:
            logger.info(f"⚠️ Erreur nettoyage processing_city: {cleanup_error}")
        
        return jsonify({
            'success': True,
            'tour_data': tour_data,
            'message': 'Tour généré avec succès'
        })
        
    except requests.Timeout as timeout_err:
        logger.info(f"⏰ Timeout pendant la génération: {timeout_err}")
        
        try:
            if place_id:
                narrando_api.migrator.supabase.table('processing_city').update({
                    'status': 'error',
                    'error_message': f"Timeout: {timeout_err}",
                    'current_step_key': 'timeout',
                    'progress_percent': 100
                }).eq('place_id', place_id).execute()
                logger.info(f"✅ Processing city marked as timeout for place_id: {place_id}")
        except Exception as cleanup_error:
            logger.info(f"⚠️ Erreur marquage timeout processing_city: {cleanup_error}")
        
        return jsonify({'error': 'Timeout during generation'}), 504

    except Exception as e:
        logger.info(f"❌ Erreur: {str(e)}")
        
        # 🔧 CRITIQUE: Marquer processing_city en erreur (pas supprimer)
        try:
            place_id = place_id if 'place_id' in locals() and place_id else ''
            if place_id:
                narrando_api.migrator.supabase.table('processing_city').update({
                    'status': 'error',
                    'error_message': str(e)
                }).eq('place_id', place_id).execute()
                logger.info(f"✅ Processing city marked as error for place_id: {place_id}")
            else:
                logger.info(f"⚠️ Cannot mark processing_city as error: place_id not available")
        except Exception as cleanup_error:
            logger.info(f"⚠️ Erreur marquage processing_city error: {cleanup_error}")
        
        return jsonify({'error': str(e)}), 500

@app.route('/generate-preview-audio/<tour_id>', methods=['POST'])
@require_token
def generate_preview_audio(tour_id):
    """
    Génère l'audio de prévisualisation d'un tour (premier point + audio)
    Body: {
        "attraction_index": 0,
        "skip_audio": false,
        "force_regenerate": false,
        "narration_type": "standard"
    }
    """
    try:
        data = request.get_json() or {}
        attraction_index = data.get('attraction_index', 0)
        skip_audio = data.get('skip_audio', False)
        force_regenerate = data.get('force_regenerate', False)
        narration_type = data.get('narration_type', 'standard')
        language_code = (data.get('language_code') or '').lower()
        if not language_code:
            return jsonify({'error': 'language_code requis'}), 400
        
        if skip_audio:
            # Juste retourner les données sans générer l'audio
            tour_data = narrando_api.migrator.get_specific_tour_by_id(tour_id)
            
            if not tour_data:
                return jsonify({'error': f'Tour avec ID {tour_id} non trouvé'}), 404
            
            if not tour_data.get('tour', {}).get('attractions'):
                return jsonify({'error': 'Tour trouvé mais aucune attraction'}), 404
            
            attractions = tour_data['tour']['attractions']
            if attraction_index >= len(attractions):
                return jsonify({'error': f'Index {attraction_index} invalide, tour a {len(attractions)} attractions'}), 400
                
            target_attraction = attractions[attraction_index]
            preview_audio = narrando_api._extract_narration_value(target_attraction.get('audio_url'), narration_type)
            preview_description = narrando_api._extract_narration_value(target_attraction.get('ai_description'), narration_type)
            if language_code != 'en':
                translation_assets = narrando_api._get_translation_assets(target_attraction.get('place_id'), language_code)
                preview_audio = narrando_api._extract_narration_value(translation_assets.get('audio_url'), narration_type) or preview_audio
                preview_description = narrando_api._extract_narration_value(translation_assets.get('ai_description'), narration_type) or preview_description
            
            _cleanup_preview_processing_record(tour_id)
            return jsonify({
                'success': True,
                'tour_info': {
                    'id': tour_data['tour']['id'],
                    'name': tour_data['tour']['name'], 
                    'total_attractions': len(attractions)
                },
                'attraction': target_attraction,
                'attraction_index': attraction_index,
                'audio_url': preview_audio,
                'description': preview_description,
                'narration_type': narration_type,
                'language_code': language_code,
                'message': 'Prévisualisation sans audio'
            })
        else:
            preview_data = narrando_api.generate_preview_audio(
                tour_id,
                attraction_index,
                force_regenerate,
                narration_type,
                language_code
            )
            _cleanup_preview_processing_record(tour_id)
            return jsonify({
                'success': True,
                'preview_data': preview_data,
                'message': 'Prévisualisation générée'
            })
        
    except Exception as e:
        logger.info(f"❌ Erreur preview: {str(e)}")
        _mark_preview_processing_error(tour_id, str(e))
        return jsonify({'error': str(e)}), 500

@app.route('/generate-complete-audio/<tour_id>', methods=['POST'])
@require_token
def generate_complete_audio(tour_id):
    """
    Génère tous les audios d'un tour complet
    Body: {
        "force_regenerate": false,
        "skip_audio": false,
        "narration_type": "standard",
        "language_code": "en"
    }
    """
    narration_type = 'standard'
    try:
        data = request.get_json() or {}
        force_regenerate = data.get('force_regenerate', False)
        skip_audio = data.get('skip_audio', False)
        narration_type = data.get('narration_type', 'standard')
        language_code = (data.get('language_code') or '').lower()
        if not language_code:
            return jsonify({'error': 'language_code requis'}), 400
        
        if skip_audio:
            if narrando_api.migrator and narrando_api.migrator.supabase:
                try:
                    narrando_api.migrator.supabase.table('processing_tour_generation') \
                        .delete() \
                        .eq('tour_id', tour_id) \
                        .eq('narration_type', narration_type) \
                        .eq('language_code', language_code) \
                        .neq('status', 'error') \
                        .execute()
                except Exception as cleanup_error:
                    logger.info(f"⚠️ Erreur suppression processing_tour_generation (skip): {cleanup_error}")
            return jsonify({
                'success': True,
                'message': 'Génération audio skippée pour les tests',
                'tour_id': tour_id,
                'generated_audios': [],
                'total_generated': 0,
                'narration_type': narration_type,
                'language_code': language_code
            })
        
        result = narrando_api.generate_complete_tour_audio(
            tour_id,
            force_regenerate,
            narration_type,
            language_code
        )
        
        if narrando_api.migrator and narrando_api.migrator.supabase:
            try:
                narrando_api.migrator.supabase.table('processing_tour_generation') \
                    .delete() \
                    .eq('tour_id', tour_id) \
                    .eq('narration_type', narration_type) \
                    .eq('language_code', language_code) \
                    .neq('status', 'error') \
                    .execute()
            except Exception as cleanup_error:
                logger.info(f"⚠️ Erreur suppression processing_tour_generation: {cleanup_error}")
        
        return jsonify({
            'success': True,
            'result': result,
            'message': 'Tour complet généré'
        })
        
    except Exception as e:
        logger.info(f"❌ Erreur tour complet: {str(e)}")
        if narrando_api.migrator and narrando_api.migrator.supabase:
            try:
                narrando_api.migrator.supabase.table('processing_tour_generation') \
                    .update({'status': 'error', 'error_message': str(e)}) \
                    .eq('tour_id', tour_id) \
                    .eq('narration_type', narration_type) \
                    .eq('language_code', language_code) \
                    .execute()
            except Exception as mark_error:
                logger.info(f"⚠️ Impossible de marquer processing_tour_generation en erreur: {mark_error}")
        return jsonify({'error': str(e)}), 500

@app.route('/generate-complete-audio-custom/<user_tour_id>', methods=['POST'])
@require_token
def generate_complete_audio_custom(user_tour_id):
    """
    Génère tous les audios d'un tour custom (user_tours)
    Body: {
        "force_regenerate": false,
        "skip_audio": false,
        "narration_type": "standard",
        "language_code": "en"
    }
    """
    narration_type = 'standard'
    try:
        data = request.get_json() or {}
        force_regenerate = data.get('force_regenerate', False)
        skip_audio = data.get('skip_audio', False)
        narration_type = data.get('narration_type', 'standard')
        language_code = (data.get('language_code') or '').lower()
        if not language_code:
            return jsonify({'error': 'language_code requis'}), 400

        if skip_audio:
            if narrando_api.migrator and narrando_api.migrator.supabase:
                try:
                    narrando_api.migrator.supabase.table('processing_user_tour_generation') \
                        .delete() \
                        .eq('user_tour_id', user_tour_id) \
                        .eq('narration_type', narration_type) \
                        .eq('language_code', language_code) \
                        .neq('status', 'error') \
                        .execute()
                except Exception as cleanup_error:
                    logger.info(f"⚠️ Erreur suppression processing_user_tour_generation (skip): {cleanup_error}")
            return jsonify({
                'success': True,
                'message': 'Génération audio custom skippée pour les tests',
                'user_tour_id': user_tour_id,
                'generated_audios': [],
                'total_generated': 0,
                'narration_type': narration_type,
                'language_code': language_code
            })

        result = narrando_api.generate_complete_user_tour_audio(
            user_tour_id,
            force_regenerate,
            narration_type,
            language_code
        )

        if narrando_api.migrator and narrando_api.migrator.supabase:
            try:
                narrando_api.migrator.supabase.table('processing_user_tour_generation') \
                    .delete() \
                    .eq('user_tour_id', user_tour_id) \
                    .eq('narration_type', narration_type) \
                    .eq('language_code', language_code) \
                    .neq('status', 'error') \
                    .execute()
            except Exception as cleanup_error:
                logger.info(f"⚠️ Erreur suppression processing_user_tour_generation: {cleanup_error}")

        return jsonify({
            'success': True,
            'result': result,
            'message': 'Tour custom complet généré'
        })

    except Exception as e:
        logger.info(f"❌ Erreur tour custom complet: {str(e)}")
        if narrando_api.migrator and narrando_api.migrator.supabase:
            try:
                narrando_api.migrator.supabase.table('processing_user_tour_generation') \
                    .update({'status': 'error'}) \
                    .eq('user_tour_id', user_tour_id) \
                    .eq('narration_type', narration_type) \
                    .eq('language_code', language_code) \
                    .execute()
            except Exception as mark_error:
                logger.info(f"⚠️ Impossible de marquer processing_user_tour_generation en erreur: {mark_error}")
        return jsonify({'error': str(e)}), 500

@app.route('/tours/<tour_id>', methods=['GET'])
def get_tour(tour_id):
    """Récupère les données d'un tour spécifique"""
    try:
        tour_data = narrando_api.migrator.get_specific_tour_by_id(tour_id)
        
        if not tour_data:
            return jsonify({'error': f'Tour avec ID {tour_id} non trouvé'}), 404
        
        return jsonify({
            'success': True,
            'tour_data': tour_data
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    logger.info("🚀 Narrando API - Démarrage...")
    logger.info(f"   AWS S3 configuré: {'✅' if s3_client else '❌'}")
    tts_provider = os.getenv('TTS_PROVIDER', 'openai').upper()
    logger.info(f"   TTS Provider: {tts_provider} {'✅' if narrando_api.tts_client.client else '❌'}")
    logger.info("   Mode: Production ready avec options skip pour tests")

    port = int(os.getenv("PORT", "5000"))
    debug_enabled = os.getenv("FLASK_DEBUG", "false").lower() in {"1", "true", "yes", "on"}
    logger.info(f"   Port: {port} | Debug: {debug_enabled}")

    app.run(host='0.0.0.0', port=port, debug=debug_enabled)
