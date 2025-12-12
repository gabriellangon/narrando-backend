"""
SupabaseMigrator - Migration transparente avec structure existante
🎯 ZÉRO modification de schema - Adaptation intelligente des données clustering
🖼️ Enrichissement automatique avec URLs Google Photos
"""
import json
import os
import sys
from datetime import datetime
from typing import Dict, Any, List, Callable

# Ajouter le répertoire parent pour importer utils
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from supabase import create_client, Client
from dotenv import load_dotenv
from utils.photo_url_generator import GooglePhotoURLGenerator
from utils.logging_config import get_logger, verbose_logging_enabled

# Charger les variables d'environnement
load_dotenv()

logger = get_logger(__name__)
VERBOSE_LOGS = verbose_logging_enabled()

class SupabaseMigrator:
    def __init__(self):
        """Initialise le migrateur - Utilise la structure existante parfaite"""
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
        self.supabase = None
        
        if not self.supabase_url or not self.supabase_key:
            logger.warning("⚠️ SUPABASE_URL ou SUPABASE_SERVICE_KEY non configurés dans .env")
            logger.warning("   L'API fonctionnera en mode dégradé sans base de données")
            return
        
        try:
            self.supabase: Client = create_client(self.supabase_url, self.supabase_key)
            logger.info("✅ Supabase connecté")
        except Exception as e:
            logger.warning("⚠️ Erreur connexion Supabase: %s", e)
            logger.warning("   L'API fonctionnera en mode dégradé sans base de données")
            self.supabase = None
        
        # Initialiser le générateur d'URLs photos
        try:
            self.photo_generator = GooglePhotoURLGenerator()
            logger.info("🚀 SupabaseMigrator - Structure existante + URLs photos !")
        except Exception as e:
            logger.warning("⚠️ Générateur photos indisponible: %s", e)
            self.photo_generator = None
    
    def load_route_data(self, file_path: str = "data/optimized_route.json") -> Dict[str, Any]:
        """Charge les données clustering depuis le fichier JSON"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Vérifier si c'est bien des données V2
            version = data.get("version", "")
            algorithm = data.get("algorithm_used", "")
            
            # Détecter V2 par version ou algorithme
            is_v2 = (version in ["V2_clustering", "V2"] or 
                    algorithm in ["Geographic_Clustering_TSP_Local"] or
                    "tours" in data)  # Structure V2 contient toujours "tours"
            
            if is_v2:
                print(f"✅ Données clustering chargées depuis {file_path} (version: {version})")
                return data
            else:
                print(f"⚠️  Données V1 détectées (version: {version}), adaptation en cours...")
                # Fallback pour l'ancien format - le convertir vers structure V2
                return self._adapt_v1_structure(data)
                
        except FileNotFoundError:
            raise FileNotFoundError(f"Le fichier {file_path} n'existe pas")
        except json.JSONDecodeError:
            raise ValueError(f"Le fichier {file_path} contient du JSON invalide")
    
    def _adapt_v1_structure(self, v1_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        🔄 Adapte les anciennes données V1 vers structure V2 transparente
        """
        print("🔄 Adaptation V1 → V2...")
        
        # Structure V2 basique pour compatibilité
        v2_data = {
            "version": "V2_clustering_adapted",
            "algorithm_used": "V1_adapted_to_V2",
            "city": v1_data.get("city", "Unknown"),
            "country": v1_data.get("country", "Unknown"),
            "place_id": v1_data.get("place_id"),
            "country_iso_code": v1_data.get("country_iso_code"),
            "clusters_count": 1,  # V1 = un seul cluster par défaut
            "tours": [],
            "guided_tours": v1_data.get("guided_tours", []),
            "walking_paths": v1_data.get("walking_paths", [])
        }
        
        # Adapter optimized_route vers tours V2
        if "optimized_route" in v1_data:
            # Créer un tour unique avec tous les points V1
            single_tour = {
                "cluster_id": 1,
                "cluster_name": "Tour Principal (V1 adapté)",
                "points": [],
                "stats": {
                    "total_distance": v1_data.get("total_distance", 0),
                    "estimated_walking_time": v1_data.get("estimated_walking_time", 0),
                    "points_count": len(v1_data["optimized_route"])
                }
            }
            
            # Convertir chaque point optimized_route vers format V2
            for i, point in enumerate(v1_data["optimized_route"]):
                point_v2 = {
                    "global_index": point.get("index", i),  # Préserver l'ordre global V1
                    "cluster_index": i,  # Ordre dans ce tour (même chose ici)
                    "name": point.get("name", "Unknown"),
                    "location": point.get("location", {}),
                    "place_id": point.get("place_id"),
                    "rating": point.get("rating"),
                    "types": point.get("types", []),
                    "formatted_address": point.get("formatted_address"),
                    "ai_description": point.get("ai_description"),
                    "distance_from_previous": point.get("distance_from_previous", 0),
                    "walking_time_from_previous": point.get("walking_time_from_previous", 0)
                }
                single_tour["points"].append(point_v2)
            
            v2_data["tours"] = [single_tour]
        
        print("✅ Adaptation V1 → V2 terminée")
        return v2_data
    
    def check_city_exists(self, city: str, country: str, place_id: str = None, country_iso_code: str = None) -> Dict[str, Any] | None:
        """Vérifie si une ville existe déjà dans la structure existante"""
        try:
            # Normaliser les noms en minuscules pour éviter les doublons de casse
            city_normalized = city.lower().strip()
            country_normalized = country.lower().strip()
            
            # 1. Vérifier d'abord par place_id si disponible (plus fiable)
            if place_id:
                place_query = self.supabase.table("cities").select("*").eq("place_id", place_id)
                place_result = place_query.execute()
                
                if place_result.data:
                    print(f"✅ Ville existante trouvée par place_id: {city}, {country}")
                    return place_result.data[0]
            
            # 2. Recherche par (ville + pays) - essayer d'abord les valeurs exactes
            city_query_exact = self.supabase.table("cities").select("*").eq("city", city.strip()).eq("country", country.strip())
            city_result_exact = city_query_exact.execute()
            
            if city_result_exact.data:
                print(f"✅ Ville existante trouvée par nom exact: {city}, {country}")
                return city_result_exact.data[0]
            
            # 3. Fallback par (ville + pays) normalisés en minuscules
            city_query_normalized = self.supabase.table("cities").select("*").eq("city", city_normalized).eq("country", country_normalized)
            city_result_normalized = city_query_normalized.execute()
            
            if city_result_normalized.data:
                print(f"✅ Ville existante trouvée par nom normalisé: {city}, {country}")
                return city_result_normalized.data[0]
            
            # 4. Recherche case-insensitive étendue (au cas où les données auraient des casses mixtes)
            all_cities = self.supabase.table("cities").select("*").execute()
            if all_cities.data:
                for existing_city in all_cities.data:
                    if (existing_city['city'].lower().strip() == city_normalized and 
                        existing_city['country'].lower().strip() == country_normalized):
                        print(f"✅ Ville existante trouvée par recherche étendue: {city}, {country}")
                        return existing_city
            
            print(f"🔍 Nouvelle ville: {city}, {country}")
            return None
                
        except Exception as e:
            print(f"❌ Erreur vérification ville: {e}")
            return None
    
    def insert_or_update_city(self, route_data: Dict[str, Any]) -> str:
        """
        Insère ou met à jour une ville - STRUCTURE EXISTANTE uniquement
        """
        try:
            city = route_data["city"]
            country = route_data["country"]
            place_id = route_data.get("place_id")
            country_iso_code = route_data.get("country_iso_code")
            
            # Normaliser les noms en minuscules pour éviter les doublons
            city_normalized = city.lower().strip()
            country_normalized = country.lower().strip()
            
            # Vérifier si la ville existe
            existing_city = self.check_city_exists(city, country, place_id, country_iso_code)
            
            # Données ville - SEULEMENT ce qui existe dans le schema avec noms normalisés
            city_data = {
                "city": city_normalized,
                "country": country_normalized,
                "place_id": place_id,
                "country_iso_code": country_iso_code,
                "updated_at": datetime.now().isoformat()
            }
            
            if existing_city:
                # Mettre à jour la ville existante
                city_id = existing_city["id"]
                print(f"🔄 Mise à jour ville existante: {city}")
                
                result = self.supabase.table("cities").update(city_data).eq("id", city_id).execute()
                
                if result.data:
                    print(f"✅ Ville mise à jour: {city_id}")
                    return city_id
            else:
                # Créer nouvelle ville
                print(f"🆕 Création nouvelle ville: {city}")
                city_data["created_at"] = datetime.now().isoformat()
                
                result = self.supabase.table("cities").insert(city_data).execute()
                
                if result.data:
                    city_id = result.data[0]["id"]
                    print(f"✅ Ville créée: {city_id}")
                    return city_id
            
            raise Exception("Échec insertion/mise à jour ville")
            
        except Exception as e:
            print(f"❌ Erreur insertion ville: {e}")
            raise
    
    def create_attractions_from_tours(self, city_id: str, tours: List[Dict[str, Any]], source_attractions: List[Dict[str, Any]] = None) -> Dict[int, str]:
        """
        Crée les attractions depuis les tours V2 - STRUCTURE EXISTANTE
        Mapping global_index → attraction_id
        """
        try:
            # 🔍 Utiliser les données sources fournies ou les charger depuis fichier
            if source_attractions is None:
                source_attractions = self._load_source_attractions_with_photos()
            
            attractions_data = []
            global_index_to_id = {}
            
            logger.info("🔄 Traitement des attractions depuis %s tours...", len(tours))
            if source_attractions:
                logger.debug("📸 Enrichissement avec %s attractions sources", len(source_attractions))
            
            for tour in tours:
                if VERBOSE_LOGS:
                    logger.debug("   📦 Tour: %s", tour.get('cluster_name', 'Unknown'))
                
                for point in tour["points"]:
                    global_index = point.get("global_index", 0)
                    
                    # Éviter les doublons si même attraction dans plusieurs tours
                    if global_index in global_index_to_id:
                        continue
                    
                    # 🔍 Enrichir avec les données sources (photos, ai_description, etc.)
                    enriched_point = self._enrich_point_with_source_data(point, source_attractions)
                    
                    # Données attraction - STRUCTURE EXISTANTE SEULEMENT
                    location = enriched_point.get("location", {})
                    logger.debug(
                        "   ↪️ %s (global_index=%s): distance=%s, walking_time=%s",
                        enriched_point.get("name"),
                        global_index,
                        point.get("distance_from_previous"),
                        point.get("walking_time_from_previous")
                    )
                    
                    attraction_data = {
                        "city_id": city_id,
                        "name": enriched_point["name"],
                        "formatted_address": enriched_point.get("formatted_address"),
                        "lat": location.get("lat", 0.0),
                        "lng": location.get("lng", 0.0),
                        "route_index": global_index,  # Ordre global préservé
                        "distance_from_previous": point.get("distance_from_previous", 0),
                        "walking_time_from_previous": point.get("walking_time_from_previous", 0),
                        "ai_description": enriched_point.get("ai_description"),
                        "place_id": enriched_point.get("place_id"),
                        "rating": enriched_point.get("rating"),
                        "types": enriched_point.get("types", []),
                        "photos": enriched_point.get("photos", []),  # Photos sources complètes
                        "created_at": datetime.now().isoformat()
                    }
                    
                    attractions_data.append(attraction_data)
            
            # Insertion en lot
            if attractions_data:
                logger.debug("🚀 Insertion de %s attractions...", len(attractions_data))
                result = self.supabase.table("attractions").insert(attractions_data).execute()
                
                if result.data:
                    # Construire le mapping global_index → attraction_id
                    for attraction in result.data:
                        global_index = attraction["route_index"]
                        global_index_to_id[global_index] = attraction["id"]
                    
                    logger.debug("✅ %s attractions créées", len(result.data))
                    return global_index_to_id
            
            return {}
            
        except Exception as e:
            logger.error("❌ Erreur création attractions: %s", e)
            raise
    
    def create_guided_tours_from_clusters(self, city_id: str, tours: List[Dict[str, Any]], 
                                        global_index_to_attraction_id: Dict[int, str]) -> List[str]:
        """
        Crée les guided_tours depuis les clusters V2 - STRUCTURE EXISTANTE
        1 cluster = 1 guided_tour
        """
        try:
            guided_tour_ids = []
            
            for i, tour in enumerate(tours):
                cluster_id = tour.get("cluster_id", i + 1)
                stats = tour.get("stats", {})
                points = tour.get("points", [])
                
                # Données guided_tour - STRUCTURE EXISTANTE SEULEMENT
                guided_tour_data = {
                    "city_id": city_id,
                    "tour_id": cluster_id,  # ID numérique du cluster
                    "tour_name": tour.get("cluster_name", f"Tour {cluster_id}"),
                    "max_participants": 3,  # Valeur par défaut
                    "total_distance": stats.get("total_distance", 0),
                    "estimated_walking_time": stats.get("estimated_walking_time", 0),
                    "point_count": len(points),
                    "start_point": points[0]["name"] if points else None,
                    "end_point": points[-1]["name"] if len(points) > 1 else None,
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat()
                }
                
                if VERBOSE_LOGS:
                    logger.debug("🔄 Création guided_tour: %s", guided_tour_data['tour_name'])
                
                # Insérer le guided_tour
                tour_result = self.supabase.table("guided_tours").insert(guided_tour_data).execute()
                
                if tour_result.data:
                    guided_tour_uuid = tour_result.data[0]["id"]
                    guided_tour_ids.append(guided_tour_uuid)
                    
                    logger.debug("✅ Guided_tour créé: %s", guided_tour_uuid)
                    
                    # Créer les tour_points pour ce guided_tour
                    self._create_tour_points_for_cluster(guided_tour_uuid, points, global_index_to_attraction_id)
            
            return guided_tour_ids
            
        except Exception as e:
            logger.error("❌ Erreur création guided_tours: %s", e)
            raise
    
    def _create_tour_points_for_cluster(self, guided_tour_uuid: str, points: List[Dict[str, Any]], 
                                       global_index_to_attraction_id: Dict[int, str]):
        """
        Crée les tour_points pour un guided_tour - STRUCTURE EXISTANTE
        """
        try:
            tour_points_data = []
            
            for cluster_index, point in enumerate(points):
                global_index = point.get("global_index", cluster_index)
                attraction_id = global_index_to_attraction_id.get(global_index)
                
                if attraction_id:
                    # Données tour_point - STRUCTURE EXISTANTE SEULEMENT
                    tour_point_data = {
                        "tour_id": guided_tour_uuid,
                        "attraction_id": attraction_id,
                        "point_order": cluster_index + 1,  # Ordre dans ce tour (1, 2, 3...)
                        "global_index": global_index,  # Ordre global préservé
                        "created_at": datetime.now().isoformat()
                    }
                    tour_points_data.append(tour_point_data)
                else:
                    if VERBOSE_LOGS:
                        logger.debug("⚠️ Attraction manquante pour global_index %s", global_index)
            
            if tour_points_data:
                result = self.supabase.table("tour_points").insert(tour_points_data).execute()
                if result.data:
                    logger.debug("  ✅ %s tour_points créés", len(result.data))
            
        except Exception as e:
            logger.error("❌ Erreur création tour_points: %s", e)
            raise
    
    
    def migrate_route_data(self, file_path: str = "data/optimized_route.json") -> bool:
        """Migration des données clustering - Mode dégradé si Supabase indisponible"""
        if not self.supabase:
            logger.warning("⚠️ Migration skippée - Supabase non disponible")
            return True  # Retourner True pour ne pas bloquer l'API
        """
        🚀 Migration complète vers structure existante - ZÉRO modification schema
        """
        try:
            logger.info("🚀 === MIGRATION CLEAN (Structure existante) ===")
            
            # 1. Charger les données (avec adaptation V1 si nécessaire)
            route_data = self.load_route_data(file_path)
            
            # 2. Insérer/Mettre à jour la ville (schema existant)
            city_id = self.insert_or_update_city(route_data)
            
            # 3. Nettoyer les anciennes données pour cette ville
            self._clean_existing_city_data(city_id)
            
            # 4. Créer les attractions depuis les tours (utilise fichier par défaut)
            tours = route_data.get("tours", [])
            global_index_to_attraction_id = self.create_attractions_from_tours(city_id, tours)
            
            # 5. Créer les guided_tours depuis les clusters
            guided_tour_ids = self.create_guided_tours_from_clusters(city_id, tours, global_index_to_attraction_id)
            
            logger.info("🎉 === MIGRATION CLEAN RÉUSSIE ===")
            logger.info("🏙️  Ville: %s, %s", route_data['city'], route_data['country'])
            logger.info("📦 Clusters: %s", len(tours))
            logger.info("🎪 Guided_tours créés: %s", len(guided_tour_ids))
            logger.info("📍 Attractions: %s", len(global_index_to_attraction_id))
            logger.info("🎯 Structure existante 100%% respectée !")
            
            return True
            
        except Exception as e:
            logger.error("💥 Erreur migration: %s", e)
            return False
    
    def migrate_route_data_with_source_attractions(self, route_data: Dict[str, Any], source_attractions: List[Dict[str, Any]]) -> bool:
        """
        🚀 Migration avec attractions sources directes (pour API)
        Évite la lecture de fichier et utilise les données fournies directement
        """
        if not self.supabase:
            logger.warning("⚠️ Migration skippée - Supabase non disponible")
            return True  # Retourner True pour ne pas bloquer l'API
        
        try:
            logger.info("🚀 === MIGRATION CLEAN AVEC DONNÉES DIRECTES ===")
            
            # 1. Insérer/Mettre à jour la ville (schema existant)
            city_id = self.insert_or_update_city(route_data)
            
            # 2. Nettoyer les anciennes données pour cette ville
            self._clean_existing_city_data(city_id)
            
            # 3. Créer les attractions depuis les tours avec source_attractions directes
            tours = route_data.get("tours", [])
            global_index_to_attraction_id = self.create_attractions_from_tours(city_id, tours, source_attractions)
            
            # 4. Créer les guided_tours depuis les clusters
            guided_tour_ids = self.create_guided_tours_from_clusters(city_id, tours, global_index_to_attraction_id)
            
            logger.info("🎉 === MIGRATION AVEC DONNÉES DIRECTES RÉUSSIE ===")
            logger.info("🏙️  Ville: %s, %s", route_data['city'], route_data['country'])
            logger.info("📦 Clusters: %s", len(tours))
            logger.info("🎪 Guided_tours créés: %s", len(guided_tour_ids))
            logger.info("📍 Attractions: %s", len(global_index_to_attraction_id))
            logger.info("📸 Source attractions avec photos: %s", len(source_attractions))
            logger.info("🎯 Structure existante 100%% respectée !")
            
            return {
                "success": True,
                "city_id": city_id,
                "tour_ids": guided_tour_ids,
                "tours_count": len(guided_tour_ids),
                "attractions_count": len(global_index_to_attraction_id)
            }
            
        except Exception as e:
            logger.error("💥 Erreur migration avec données directes: %s", e)
            return {
                "success": False,
                "error": str(e),
                "tour_ids": [],
                "tours_count": 0,
                "attractions_count": 0
            }
    
    def _clean_existing_city_data(self, city_id: str):
        """Nettoie les anciennes données pour une ville (structure existante) - TOUTES LES TABLES"""
        try:
            logger.info("🧹 Nettoyage complet des données existantes...")
            
            # Récupérer tous les guided_tours de cette ville pour les suppressions en cascade
            guided_tours_result = self.supabase.table("guided_tours").select("id").eq("city_id", city_id).execute()
            guided_tour_ids = [row["id"] for row in guided_tours_result.data]
            
            if guided_tour_ids:
                if VERBOSE_LOGS:
                    logger.debug("   🎪 %s guided_tours trouvés à nettoyer", len(guided_tour_ids))
                
                # Récupérer tous les tour_purchases pour ces tours
                purchases_result = self.supabase.table("tour_purchases").select("id").in_("tour_id", guided_tour_ids).execute()
                purchase_ids = [row["id"] for row in purchases_result.data]
                
                if purchase_ids:
                    if VERBOSE_LOGS:
                        logger.debug("   💰 %s tour_purchases trouvés à nettoyer", len(purchase_ids))
                    
                    # 1. tour_participants (dépend de tour_purchases)
                    participants_result = self.supabase.table("tour_participants").delete().in_("tour_purchase_id", purchase_ids).execute()
                    if VERBOSE_LOGS:
                        logger.debug("   👥 %s tour_participants supprimés", len(participants_result.data) if participants_result.data else 0)
                    
                    # 2. tour_invitations (dépend de tour_purchases)
                    invitations_result = self.supabase.table("tour_invitations").delete().in_("tour_purchase_id", purchase_ids).execute()
                    if VERBOSE_LOGS:
                        logger.debug("   📮 %s tour_invitations supprimées", len(invitations_result.data) if invitations_result.data else 0)
                    
                    # 3. tour_purchases (dépend de guided_tours)
                    purchases_delete_result = self.supabase.table("tour_purchases").delete().in_("tour_id", guided_tour_ids).execute()
                    if VERBOSE_LOGS:
                        logger.debug("   💰 %s tour_purchases supprimés", len(purchases_delete_result.data) if purchases_delete_result.data else 0)
                
                # 4. walking_paths (dépend de guided_tours)
                walking_paths_result = self.supabase.table("walking_paths").delete().in_("tour_id", guided_tour_ids).execute()
                if VERBOSE_LOGS:
                    logger.debug("   🚶 %s walking_paths supprimés", len(walking_paths_result.data) if walking_paths_result.data else 0)
                
                # 5. tour_points (dépend de guided_tours)  
                tour_points_result = self.supabase.table("tour_points").delete().in_("tour_id", guided_tour_ids).execute()
                if VERBOSE_LOGS:
                    logger.debug("   📍 %s tour_points supprimés", len(tour_points_result.data) if tour_points_result.data else 0)
                
                # 6. guided_tours (dépend de cities)
                guided_tours_delete_result = self.supabase.table("guided_tours").delete().eq("city_id", city_id).execute()
                if VERBOSE_LOGS:
                    logger.debug("   🎪 %s guided_tours supprimés", len(guided_tours_delete_result.data) if guided_tours_delete_result.data else 0)
            
            # 7. attractions (dépend de cities)
            attractions_result = self.supabase.table("attractions").delete().eq("city_id", city_id).execute()
            logger.info("   🏛️  %s attractions supprimées", len(attractions_result.data) if attractions_result.data else 0)
            
            logger.info("✅ Nettoyage complet terminé - TOUTES les données liées supprimées")
            
        except Exception as e:
            logger.error("❌ Erreur nettoyage complet: %s", e)
            # Re-raise l'exception car un nettoyage partiel peut causer des incohérences
            raise
    
    def _load_source_attractions_with_photos(self) -> List[Dict[str, Any]]:
        """
        🔍 Charge les données sources complètes avec photos depuis filtered_attractions.json
        """
        try:
            source_file = "data/filtered_attractions.json"
            
            if not os.path.exists(source_file):
                logger.debug("⚠️  Fichier source %s non trouvé - pas d'enrichissement photos", source_file)
                return []
            
            with open(source_file, 'r', encoding='utf-8') as f:
                source_data = json.load(f)
            
            attractions = source_data.get("filtered_attractions", [])
            logger.debug("📸 %s attractions sources chargées avec photos", len(attractions))
            return attractions
            
        except Exception as e:
            logger.warning("⚠️  Erreur chargement sources: %s", e)
            return []
    
    def _enrich_point_with_source_data(self, point: Dict[str, Any], source_attractions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        🔍 Enrichit un point de tour avec les données complètes sources (photos, descriptions, etc.)
        """
        if not source_attractions:
            return point
        
        # Rechercher l'attraction source correspondante par place_id ou nom
        place_id = point.get("place_id")
        point_name = point.get("name", "").strip().lower()
        
        matching_source = None
        
        # 1. Recherche par place_id (plus précise)
        if place_id:
            for source in source_attractions:
                if source.get("place_id") == place_id:
                    matching_source = source
                    break
        
        # 2. Fallback : recherche par nom (moins précise)
        if not matching_source and point_name:
            for source in source_attractions:
                source_name = source.get("name", "").strip().lower()
                if source_name == point_name:
                    matching_source = source
                    break
        
        if matching_source:
            # Enrichir le point avec toutes les données sources
            enriched = point.copy()
            
            # Préserver les données spécifiques du point (distances, indices, etc.)
            # mais enrichir avec les données complètes sources
            for key, value in matching_source.items():
                if key not in ["global_index", "cluster_index", "distance_from_previous", "walking_time_from_previous"]:
                    enriched[key] = value
            
            if VERBOSE_LOGS:
                logger.debug("  📸 Enrichi: %s → %s photos", point_name, len(matching_source.get('photos', [])))
            return enriched
        else:
            if VERBOSE_LOGS:
                logger.debug("  ⚠️  Source non trouvée: %s", point_name)
            return point

    def get_specific_tour_by_id(self, tour_id: str) -> Dict[str, Any] | None:
        """
        Récupère un tour spécifique par son guided_tour UUID
        """
        if not self.supabase:
            print("❌ Supabase non disponible")
            return None
            
        try:
            # Utiliser la vue optimisée guided_tours_with_points
            tour_result = self.supabase.table("guided_tours_with_points").select("*").eq("id", tour_id).execute()
            
            if not tour_result.data:
                print(f"❌ Tour non trouvé: {tour_id}")
                return None
            
            tour = tour_result.data[0]
            
            # Récupérer les infos de la ville
            city_result = self.supabase.table("cities").select("*").eq("id", tour['city_id']).execute()
            city_data = city_result.data[0] if city_result.data else None
            
            # Formater les attractions depuis la vue
            attractions = []
            if tour.get('points'):
                for point in tour['points']:
                    if point.get('attraction'):
                        attraction = point['attraction']
                        location = attraction.get('location') or {
                            'lat': attraction.get('lat'),
                            'lng': attraction.get('lng')
                        }
                        attractions.append({
                            'id': attraction.get('id'),  # UUID de l'attraction en base
                            'place_id': attraction.get('place_id'),
                            'name': attraction['name'],
                            'formatted_address': attraction.get('formatted_address'),
                            'rating': attraction.get('rating'),
                            'ai_description': attraction.get('ai_description'),
                            'audio_url': attraction.get('audio_url'),
                            'types': attraction.get('types'),
                            'photos': attraction.get('photos'),
                            'point_order': point['point_order'],
                            'global_index': point['global_index'],
                            'location': location
                        })
            
            return {
                'tour': {
                    'id': tour['id'],
                    'name': tour['tour_name'],
                    'estimated_walking_time': tour['estimated_walking_time'],
                    'point_count': tour['point_count'],
                    'attractions': attractions
                },
                'city': city_data,
                'total_attractions': len(attractions)
            }
            
        except Exception as e:
            print(f"❌ Erreur get_specific_tour_by_id: {e}")
            return None

    def get_specific_user_tour_by_id(self, user_tour_id: str) -> Dict[str, Any] | None:
        """
        Récupère un tour custom (user_tours) avec ses points et attractions.
        """
        if not self.supabase:
            print("❌ Supabase non disponible")
            return None

        try:
            tour_result = self.supabase.table("user_tours").select("*").eq("id", user_tour_id).execute()

            if not tour_result.data:
                print(f"❌ Tour custom non trouvé: {user_tour_id}")
                return None

            tour = tour_result.data[0]

            city_data = None
            if tour.get('city_id'):
                city_result = self.supabase.table("cities").select("*").eq("id", tour['city_id']).execute()
                city_data = city_result.data[0] if city_result.data else None

            points_result = self.supabase.table("user_tour_points").select(
                "id, point_order, global_index, attraction:attractions(id, place_id, name, formatted_address, rating, ai_description, audio_url, types, photos, lat, lng)"
            ).eq("user_tour_id", user_tour_id).order("point_order").execute()

            attractions: List[Dict[str, Any]] = []
            for point in points_result.data or []:
                attraction = point.get('attraction') or {}
                location = {
                    'lat': float(attraction['lat']) if attraction.get('lat') is not None else None,
                    'lng': float(attraction['lng']) if attraction.get('lng') is not None else None
                }
                attractions.append({
                    'id': attraction.get('id'),
                    'place_id': attraction.get('place_id'),
                    'name': attraction.get('name'),
                    'formatted_address': attraction.get('formatted_address'),
                    'rating': attraction.get('rating'),
                    'ai_description': attraction.get('ai_description'),
                    'audio_url': attraction.get('audio_url'),
                    'types': attraction.get('types'),
                    'photos': attraction.get('photos'),
                    'point_order': point.get('point_order'),
                    'global_index': point.get('global_index'),
                    'location': location
                })

            attractions = [a for a in attractions if a.get('place_id')]

            return {
                'tour': {
                    'id': tour['id'],
                    'name': tour.get('name'),
                    'estimated_walking_time': tour.get('estimated_walking_time'),
                    'point_count': tour.get('point_count') or len(attractions),
                    'attractions': attractions
                },
                'city': city_data,
                'total_attractions': len(attractions)
            }

        except Exception as e:
            print(f"❌ Erreur get_specific_user_tour_by_id: {e}")
            return None

    def ensure_walking_paths_for_tour(
        self,
        tour_id: str,
        ordered_attractions: List[Dict[str, Any]],
        path_builder: Callable[[Dict[str, float], Dict[str, float]], List[Dict[str, float]]],
    ) -> None:
        """
        Génère et insère les walking_paths pour un tour en s'appuyant sur les attractions actuelles.
        """
        if not self.supabase:
            raise ValueError("Supabase non disponible pour générer les walking_paths")

        ordered_attractions = ordered_attractions or []
        expected_segments = max(len(ordered_attractions) - 1, 0)

        existing = self.supabase.table("walking_paths").select("id").eq("tour_id", tour_id).execute()
        existing_count = len(existing.data or [])

        if not ordered_attractions:
            if existing_count:
                self.supabase.table("walking_paths").delete().eq("tour_id", tour_id).execute()
            return

        if len(ordered_attractions) == 1:
            if existing_count:
                self.supabase.table("walking_paths").delete().eq("tour_id", tour_id).execute()

            point = ordered_attractions[0]
            attraction_id = point.get("id")
            location = point.get("location") or {}
            lat = location.get("lat")
            lng = location.get("lng")
            if attraction_id is None or lat is None or lng is None:
                raise ValueError(
                    f"Attraction unique invalide pour walking_path (tour {tour_id})"
                )

            coord = [{"lat": float(lat), "lng": float(lng)}]
            result = self.supabase.table("walking_paths").insert([{
                "tour_id": tour_id,
                "from_attraction_id": attraction_id,
                "to_attraction_id": attraction_id,
                "path_coordinates": coord,
                "created_at": datetime.now().isoformat()
            }]).execute()
            logger.debug("🚶 Walking_path unique généré pour le tour %s", tour_id)
            return

        if existing_count == expected_segments:
            return

        # Purger les anciens chemins avant de recalculer
        if existing_count:
            self.supabase.table("walking_paths").delete().eq("tour_id", tour_id).execute()

        walking_paths_data: List[Dict[str, Any]] = []

        for idx in range(expected_segments):
            current = ordered_attractions[idx]
            nxt = ordered_attractions[idx + 1]

            origin = current.get("location")
            destination = nxt.get("location")
            if not origin or not destination:
                raise ValueError(
                    f"Coordonnées manquantes pour calculer le chemin entre "
                    f"{current.get('name')} et {nxt.get('name')}"
                )

            path_coordinates = path_builder(origin, destination)
            if not path_coordinates:
                raise ValueError(
                    f"Chemin vide pour la paire {current.get('name')} → {nxt.get('name')}"
                )

            walking_paths_data.append({
                "tour_id": tour_id,
                "from_attraction_id": current.get("id"),
                "to_attraction_id": nxt.get("id"),
                "path_coordinates": path_coordinates,
                "created_at": datetime.now().isoformat()
            })

        if not walking_paths_data:
            raise ValueError(f"Aucun walking_path généré pour le tour {tour_id}")

        insert_result = self.supabase.table("walking_paths").insert(walking_paths_data).execute()
        logger.debug("🚶 %s walking_paths générés pour le tour %s", len(insert_result.data or []), tour_id)

    def ensure_user_walking_paths_for_tour(
        self,
        user_tour_id: str,
        ordered_attractions: List[Dict[str, Any]],
        path_builder: Callable[[Dict[str, float], Dict[str, float]], List[Dict[str, float]]],
    ) -> None:
        """
        Génère et insère les walking_paths pour un tour custom (user_tours).
        """
        if not self.supabase:
            raise ValueError("Supabase non disponible pour générer les walking_paths custom")

        ordered_attractions = ordered_attractions or []
        expected_segments = max(len(ordered_attractions) - 1, 0)

        existing = self.supabase.table("user_walking_paths").select("id").eq("user_tour_id", user_tour_id).execute()
        existing_count = len(existing.data or [])

        if not ordered_attractions:
            if existing_count:
                self.supabase.table("user_walking_paths").delete().eq("user_tour_id", user_tour_id).execute()
            return

        if len(ordered_attractions) == 1:
            if existing_count:
                self.supabase.table("user_walking_paths").delete().eq("user_tour_id", user_tour_id).execute()

            point = ordered_attractions[0]
            attraction_id = point.get("id")
            location = point.get("location") or {}
            lat = location.get("lat")
            lng = location.get("lng")
            if attraction_id is None or lat is None or lng is None:
                raise ValueError(
                    f"Attraction unique invalide pour walking_path custom (tour {user_tour_id})"
                )

            coord = [{"lat": float(lat), "lng": float(lng)}]
            self.supabase.table("user_walking_paths").insert([{
                "user_tour_id": user_tour_id,
                "from_attraction_id": attraction_id,
                "to_attraction_id": attraction_id,
                "path_coordinates": coord,
                "created_at": datetime.now().isoformat()
            }]).execute()
            logger.debug("🚶 Walking_path unique généré pour le tour custom %s", user_tour_id)
            return

        if existing_count == expected_segments:
            return

        if existing_count:
            self.supabase.table("user_walking_paths").delete().eq("user_tour_id", user_tour_id).execute()

        walking_paths_data: List[Dict[str, Any]] = []

        for idx in range(expected_segments):
            current = ordered_attractions[idx]
            nxt = ordered_attractions[idx + 1]

            origin = current.get("location")
            destination = nxt.get("location")
            if not origin or not destination:
                raise ValueError(
                    f"Coordonnées manquantes pour calculer le chemin (custom) entre "
                    f"{current.get('name')} et {nxt.get('name')}"
                )

            path_coordinates = path_builder(origin, destination)
            if not path_coordinates:
                raise ValueError(
                    f"Chemin vide pour la paire custom {current.get('name')} → {nxt.get('name')}"
                )

            walking_paths_data.append({
                "user_tour_id": user_tour_id,
                "from_attraction_id": current.get("id"),
                "to_attraction_id": nxt.get("id"),
                "path_coordinates": path_coordinates,
                "created_at": datetime.now().isoformat()
            })

        if not walking_paths_data:
            raise ValueError(f"Aucun walking_path généré pour le tour custom {user_tour_id}")

        insert_result = self.supabase.table("user_walking_paths").insert(walking_paths_data).execute()
        logger.debug("🚶 %s walking_paths générés pour le tour custom %s", len(insert_result.data or []), user_tour_id)

    def get_tour_by_id(self, tour_id: str) -> Dict[str, Any] | None:
        """
        Récupère un tour complet par son ID ou critères de recherche
        """
        if not self.supabase:
            print("❌ Supabase non disponible")
            return None
            
        try:
            # Essayer d'abord par city_id direct
            city_result = self.supabase.table("cities").select("*").eq("id", tour_id).execute()
            
            if not city_result.data:
                # Essayer par place_id ou nom de ville
                city_result = self.supabase.table("cities").select("*").eq("place_id", tour_id).execute()
            
            if not city_result.data:
                print(f"❌ Tour non trouvé: {tour_id}")
                return None
            
            city_data = city_result.data[0]
            city_id = city_data['id']
            
            # Récupérer les guided_tours
            tours_result = self.supabase.table("guided_tours").select("""
                id, name, estimated_duration_minutes, tour_order,
                tour_points (
                    id, position_in_tour, visit_duration_minutes,
                    attractions (
                        id, place_id, name, formatted_address, rating, 
                        ai_description, audio_url, types, photos
                    )
                )
            """).eq("city_id", city_id).order("tour_order").execute()
            
            # Formater les données pour l'API
            formatted_tours = []
            for tour in tours_result.data:
                tour_attractions = []
                if tour.get('tour_points'):
                    for point in sorted(tour['tour_points'], key=lambda x: x['position_in_tour']):
                        if point.get('attractions'):
                            attraction = point['attractions']
                            tour_attractions.append({
                                'place_id': attraction['place_id'],
                                'name': attraction['name'],
                                'formatted_address': attraction['formatted_address'],
                                'rating': attraction['rating'],
                                'ai_description': attraction['ai_description'],
                                'audio_url': attraction['audio_url'],
                                'types': attraction['types'],
                                'photos': attraction['photos'],
                                'visit_duration_minutes': point['visit_duration_minutes']
                            })
                
                formatted_tours.append({
                    'id': tour['id'],
                    'name': tour['name'],
                    'estimated_duration_minutes': tour['estimated_duration_minutes'],
                    'tour_order': tour['tour_order'],
                    'attractions': tour_attractions
                })
            
            return {
                'city': city_data,
                'tours': formatted_tours,
                'total_tours': len(formatted_tours)
            }
            
        except Exception as e:
            print(f"❌ Erreur get_tour_by_id: {e}")
            return None

    def _merge_narration_json(self, existing: Any, narration_type: str, new_value: Any) -> Dict[str, Any]:
        """
        Fusionne une valeur de narration dans un champ JSONB (ai_description/audio_url)
        """
        if existing is None:
            merged: Dict[str, Any] = {}
        elif isinstance(existing, dict):
            merged = dict(existing)
        elif isinstance(existing, str):
            merged = {'standard': existing}
        else:
            merged = dict(existing)
        
        if new_value is None:
            merged.pop(narration_type, None)
        else:
            merged[narration_type] = new_value
        
        return merged

    def update_attraction_description(self, place_id: str, description: str, narration_type: str = "standard", language_code: str = "en") -> bool:
        """
        Met à jour la description AI d'une attraction pour un type de narration donné
        """
        if not self.supabase:
            print("❌ Supabase non disponible - description non sauvegardée")
            return False
            
        try:
            if language_code == 'en':
                existing = self.supabase.table("attractions").select("ai_description")\
                    .eq("place_id", place_id).execute()
                
                if not existing.data:
                    print(f"❌ Attraction non trouvée: {place_id}")
                    return False
                
                merged_description = self._merge_narration_json(
                    existing.data[0].get("ai_description"),
                    narration_type,
                    description
                )
                
                result = self.supabase.table("attractions").update({
                    "ai_description": merged_description,
                    "updated_at": datetime.now().isoformat()
                }).eq("place_id", place_id).execute()
                
                if result.data:
                    print(f"✅ Description ({narration_type}) mise à jour pour {place_id}")
                    return True
                else:
                    print(f"❌ Attraction non trouvée lors de la mise à jour: {place_id}")
                    return False
            else:
                translation_saved = self._upsert_attraction_translation(
                    place_id,
                    language_code,
                    narration_type,
                    description=description
                )
                if translation_saved:
                    print(f"✅ Description ({narration_type}, {language_code}) mise à jour pour {place_id}")
                return translation_saved
                
        except Exception as e:
            print(f"❌ Erreur update_attraction_description: {e}")
            return False

    def update_attraction_audio_url(self, place_id: str, audio_url: str, narration_type: str = "standard", language_code: str = "en") -> bool:
        """
        Met à jour l'URL audio d'une attraction pour un type de narration donné
        """
        if not self.supabase:
            print("❌ Supabase non disponible - URL audio non sauvegardée")
            return False
            
        try:
            if language_code == 'en':
                existing = self.supabase.table("attractions").select("audio_url")\
                    .eq("place_id", place_id).execute()
                
                if not existing.data:
                    print(f"❌ Attraction non trouvée: {place_id}")
                    return False
                
                merged_audio = self._merge_narration_json(
                    existing.data[0].get("audio_url"),
                    narration_type,
                    audio_url
                )
                
                result = self.supabase.table("attractions").update({
                    "audio_url": merged_audio,
                    "updated_at": datetime.now().isoformat()
                }).eq("place_id", place_id).execute()
                
                if result.data:
                    print(f"✅ Audio URL ({narration_type}) mise à jour pour {place_id}")
                    return True
                else:
                    print(f"❌ Attraction non trouvée lors de la mise à jour: {place_id}")
                    return False
            else:
                translation_saved = self._upsert_attraction_translation(
                    place_id,
                    language_code,
                    narration_type,
                    audio_url=audio_url
                )
                if translation_saved:
                    print(f"✅ Audio URL ({narration_type}, {language_code}) mise à jour pour {place_id}")
                return translation_saved
                
        except Exception as e:
            print(f"❌ Erreur update_attraction_audio_url: {e}")
            return False

    def _upsert_attraction_translation(
        self,
        place_id: str,
        language_code: str,
        narration_type: str,
        description: str = None,
        audio_url: str = None
    ) -> bool:
        try:
            attraction = self.supabase.table("attractions").select("id,name")\
                .eq("place_id", place_id).execute()
            if not attraction.data:
                print(f"❌ Attraction non trouvée pour traduction: {place_id}")
                return False
            attraction_id = attraction.data[0]["id"]
            base_name = attraction.data[0]["name"]

            translation = self.supabase.table("attraction_translations").select("id,name,ai_description,audio_url")\
                .eq("attraction_id", attraction_id)\
                .eq("language_code", language_code)\
                .execute()
            translation_row = translation.data[0] if translation.data else {}
            translation_name = translation_row.get("name") or base_name

            # Préparer JSON existants
            desc_payload = translation_row.get("ai_description")
            audio_payload = translation_row.get("audio_url") or {}
            try:
                desc_map = json.loads(desc_payload) if desc_payload else {}
            except Exception:
                desc_map = {}
            audio_map = dict(audio_payload) if isinstance(audio_payload, dict) else {}

            if description is not None:
                desc_map = self._merge_narration_json(desc_map, narration_type, description)
            if audio_url is not None:
                audio_map = self._merge_narration_json(audio_map, narration_type, audio_url)

            payload = {
                "attraction_id": attraction_id,
                "language_code": language_code,
                "name": translation_name,
                "updated_at": datetime.now().isoformat()
            }
            if translation_row.get("id"):
                payload["id"] = translation_row["id"]
            if description is not None:
                payload["ai_description"] = json.dumps(desc_map)
            elif translation_row.get("ai_description"):
                payload["ai_description"] = translation_row["ai_description"]

            if audio_url is not None:
                payload["audio_url"] = audio_map
            elif translation_row.get("audio_url"):
                payload["audio_url"] = translation_row["audio_url"]

            self.supabase.table("attraction_translations")\
                .upsert(payload, on_conflict="attraction_id,language_code")\
                .execute()
            return True
        except Exception as e:
            print(f"❌ Erreur upsert attraction_translation: {e}")
            return False

    def get_city_by_place_id(self, place_id: str) -> Dict[str, Any] | None:
        """
        Récupère une ville par son Place ID Google
        """
        if not self.supabase:
            print("❌ Supabase non disponible")
            return None
            
        try:
            result = self.supabase.table("cities").select("*").eq("place_id", place_id).execute()
            
            if result.data:
                return result.data[0]
            else:
                return None
                
        except Exception as e:
            print(f"❌ Erreur get_city_by_place_id: {e}")
            return None


if __name__ == "__main__":
    print("🧪 Test Migration Clean")
    
    try:
        migrator = SupabaseMigrator()
        success = migrator.migrate_route_data()
        
        if success:
            print("🎉 Migration réussie !")
        else:
            print("❌ Migration échouée")
            
    except Exception as e:
        print(f"💥 Erreur critique: {e}")
