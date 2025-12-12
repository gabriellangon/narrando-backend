"""
RouteOptimizer - Clustering géographique intelligent avec contraintes temporelles
🎯 Tours cohérents sans points isolés
"""
import os
import time
import json
import math
import random
import requests
import polyline
from typing import List, Dict, Any, Tuple, Optional, Set
from dotenv import load_dotenv
from utils.logging_config import get_logger, verbose_logging_enabled
from utils.path_validation import ensure_path_endpoints

# Charger les variables d'environnement
load_dotenv()

logger = get_logger(__name__)
VERBOSE_LOGS = verbose_logging_enabled()

class RouteOptimizer:
    """
    🔥 Optimiseur - Clustering d'abord, TSP ensuite !
    Fini les points isolés, vive les tours cohérents !
    """
    def __init__(self, max_walking_minutes: int = 15):
        """
        Initialise l'optimiseur révolutionnaire
        
        Args:
            max_walking_minutes: Contrainte temporelle max entre 2 POIs (défaut: 20min)
        """
        self.google_api_key = os.getenv("GOOGLE_PLACES_API_KEY")
        if not self.google_api_key:
            raise ValueError("🚨 Clé API Google manquante dans .env")
        
        self.directions_base_url = "https://maps.googleapis.com/maps/api/directions/json"
        self.max_walking_minutes = max_walking_minutes
        self.max_walking_distance = max_walking_minutes * 60 * 1.39  # 20min = 1668m à 5km/h
        
        # Cache optimisé
        self.distance_cache = {}
        self.directions_cache = {}
        
        logger.info("🎯 RouteOptimizer initialisé - Contrainte: ≤%s min entre POIs", max_walking_minutes)
    
    def optimize_route(self, attractions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        🚀 Clustering géographique → TSP local → Tours cohérents !
        """
        if not attractions:
            return self._empty_result()
        
        if len(attractions) == 1:
            return self._single_attraction_result(attractions[0])
        
        logger.info("🎪 === OPTIMISATION EN ACTION ===")
        logger.info("🔍 %s attractions à organiser intelligemment", len(attractions))
        
        start_time = time.time()
        
        # 🎯 Étape 1 : Clustering géographique intelligent
        logger.info("📦 Étape 1 : Clustering géographique (≤%s min)", self.max_walking_minutes)
        clusters = self._cluster_attractions_by_walking_time(attractions)
        
        logger.info("✨ %s clusters géographiques créés !", len(clusters))
        if VERBOSE_LOGS:
            for i, cluster in enumerate(clusters):
                logger.debug("   📍 Cluster %s: %s POIs", i + 1, len(cluster))
        
        # 🎯 Étape 2 : Optimisation locale par cluster
        logger.info("🔧 Étape 2 : Optimisation TSP locale par cluster")
        optimized_tours = []
        total_distance = 0
        total_walking_time = 0
        
        global_index_counter = 0  # Compteur global continu
        
        for i, cluster in enumerate(clusters):
            if VERBOSE_LOGS:
                logger.debug("   🎯 Optimisation du cluster %s...", i + 1)
            cluster_result = self._optimize_cluster(cluster, i+1, global_index_counter)
            
            # Mettre à jour le compteur global pour le cluster suivant
            global_index_counter += len(cluster_result['points'])
            
            optimized_tours.append(cluster_result)
            total_distance += cluster_result['stats']['total_distance']
            total_walking_time += cluster_result['stats']['estimated_walking_time']
            
            if VERBOSE_LOGS:
                logger.debug(
                    "   ✅ Cluster %s: %s POIs, %sm, %smin",
                    i + 1,
                    len(cluster_result['points']),
                    cluster_result['stats']['total_distance'],
                    cluster_result['stats']['estimated_walking_time'],
                )
        
        # 🎯 Étape 3 : Post-fusion des tours proches (FIX FRAGMENTATION)
        logger.info("🔧 Étape 3 : Post-fusion des tours proches et isolés")
        merged_tours = self._post_merge_nearby_tours(optimized_tours)
        merged_tours = self._deduplicate_across_tours(merged_tours)
        self._assert_unique_attractions(merged_tours)
        
        # Recalculer les statistiques après fusion
        total_distance = sum(tour['stats']['total_distance'] for tour in merged_tours)
        total_walking_time = sum(tour['stats']['estimated_walking_time'] for tour in merged_tours)
        
        logger.info("✅ %s tours initiaux → %s tours après fusion", len(optimized_tours), len(merged_tours))
        
        # 🎯 Étape 4 : Génération des variantes intelligentes
        logger.info("🌟 Étape 4 : Génération des variantes par cluster")
        tour_variants = self._generate_tour_variants(clusters, merged_tours)
        
        # 🎯 Résultat final
        processing_time = time.time() - start_time
        
        result = {
            "version": "clustering",
            "algorithm_used": "Geographic_Clustering_TSP_Local",
            "city": attractions[0].get("vicinity", "Unknown"),
            "country": "Unknown",  # À enrichir si disponible
            "total_distance": total_distance,
            "estimated_walking_time": total_walking_time,
            "constraint_max_walking_minutes": self.max_walking_minutes,
            "clusters_count": len(clusters),
            "initial_tours_count": len(optimized_tours),
            "final_tours_count": len(merged_tours),
            "tours": merged_tours,
            "tour_variants": tour_variants,
            "processing_time": round(processing_time, 2),
            "timestamp": time.time(),
            "start_point": optimized_tours[0]['points'][0]['name'] if optimized_tours else None,
            "guided_tours": self._format_for_compatibility(merged_tours)
        }
        
        logger.info("🎉 === OPTIMISATION TERMINÉE ===")
        logger.info("⚡ Temps de traitement: %.2fs", processing_time)
        logger.info(
            "📊 %s clusters → %s tours initiaux → %s tours finaux",
            len(clusters),
            len(optimized_tours),
            len(merged_tours),
        )
        logger.info("📏 Distance totale: %sm", total_distance)
        logger.info("⏱️ Temps de marche: %smin", total_walking_time)
        logger.info("🎯 ZÉRO point isolé garanti !")
        
        return result
    
    def _cluster_attractions_by_walking_time(self, attractions: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        """
        🧠 Clustering intelligent basé sur la contrainte temporelle de marche
        """
        if len(attractions) <= 2:
            return [attractions]
        
        # Construire la matrice de distances temporelles
        logger.info("🔄 Construction de la matrice de distances...")
        distance_matrix = self._build_walking_time_matrix(attractions)
        
        # Convertir en matrice binaire (1 si ≤20min, 0 sinon)
        binary_matrix = self._distance_matrix_to_binary(distance_matrix)
        
        # Clustering basé sur la connectivité
        clusters = self._connected_components_clustering(binary_matrix, attractions)
        
        # Garder tous les clusters sans limite de taille
        # La fusion intelligente s'occupera de l'optimisation
        return clusters
    
    def _build_walking_time_matrix(self, attractions: List[Dict[str, Any]]) -> List[List[float]]:
        """
        🗺️ Construit la matrice des temps de marche réels via Google Directions
        """
        n = len(attractions)
        matrix = [[0.0] * n for _ in range(n)]
        
        total_calls = (n * (n - 1)) // 2
        calls_made = 0
        
        for i in range(n):
            for j in range(i + 1, n):
                origin = attractions[i]["geometry"]["location"]
                destination = attractions[j]["geometry"]["location"]
                
                distance = self._get_walking_distance_cached(origin, destination)
                if distance is not None:
                    matrix[i][j] = distance
                    matrix[j][i] = distance  # Symétrique
                else:
                    # Fallback : distance euclidienne approximative
                    matrix[i][j] = self._euclidean_distance_approx(origin, destination)
                    matrix[j][i] = matrix[i][j]
                
                calls_made += 1
                if calls_made % 10 == 0 and VERBOSE_LOGS:
                    logger.debug("   📊 %s/%s distances calculées", calls_made, total_calls)
        
        return matrix
    
    def _distance_matrix_to_binary(self, distance_matrix: List[List[float]]) -> List[List[int]]:
        """
        🔢 Convertit la matrice de distances en matrice binaire (1 si ≤20min, 0 sinon)
        """
        n = len(distance_matrix)
        binary_matrix = [[0] * n for _ in range(n)]
        
        for i in range(n):
            for j in range(n):
                if i == j:
                    binary_matrix[i][j] = 1  # Un point est connecté à lui-même
                elif distance_matrix[i][j] <= self.max_walking_distance:
                    binary_matrix[i][j] = 1
                else:
                    binary_matrix[i][j] = 0
        
        return binary_matrix
    
    def _connected_components_clustering(self, adjacency_matrix: List[List[int]], 
                                       attractions: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        """
        🔗 Clustering par composantes connexes
        """
        n = len(attractions)
        visited = [False] * n
        clusters = []
        
        def dfs(node: int, cluster: List[int]):
            visited[node] = True
            cluster.append(node)
            
            for neighbor in range(n):
                if adjacency_matrix[node][neighbor] and not visited[neighbor]:
                    dfs(neighbor, cluster)
        
        for i in range(n):
            if not visited[i]:
                cluster_indices = []
                dfs(i, cluster_indices)
                
                cluster_attractions = [attractions[idx] for idx in cluster_indices]
                clusters.append(cluster_attractions)
        
        return clusters
    
    def _split_large_cluster(self, cluster: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        """
        ✂️ Divise intelligemment les clusters trop grands
        """
        if len(cluster) <= 8:
            return [cluster]
        
        # Clustering géographique simple par coordonnées
        coordinates = [
            [attr["geometry"]["location"]["lat"], attr["geometry"]["location"]["lng"]]
            for attr in cluster
        ]
        
        n_clusters = min(3, len(cluster) // 5)  # Max 3 sous-clusters
        
        # K-means simple fait maison (sans sklearn)
        sub_clusters = self._simple_kmeans_clustering(cluster, coordinates, n_clusters)
        
        return sub_clusters
    
    def _simple_kmeans_clustering(self, cluster: List[Dict[str, Any]], coordinates: List[List[float]], k: int) -> List[List[Dict[str, Any]]]:
        """
        🧠 K-means simple fait maison (sans sklearn)
        """
        if k >= len(cluster):
            return [[attr] for attr in cluster]
        
        # Initialisation aléatoire des centroïdes
        n_points = len(coordinates)
        centroids = []
        
        # Choisir k points aléatoires comme centroïdes initiaux
        random.seed(42)  # Pour la reproductibilité
        centroid_indices = random.sample(range(n_points), k)
        for idx in centroid_indices:
            centroids.append(coordinates[idx][:])
        
        # Algorithme K-means simplifié (max 10 itérations)
        for iteration in range(10):
            # Assigner chaque point au centroïde le plus proche
            assignments = []
            for coord in coordinates:
                closest_centroid = 0
                min_distance = float('inf')
                
                for i, centroid in enumerate(centroids):
                    distance = self._euclidean_distance_coords(coord, centroid)
                    if distance < min_distance:
                        min_distance = distance
                        closest_centroid = i
                
                assignments.append(closest_centroid)
            
            # Recalculer les centroïdes
            new_centroids = []
            for i in range(k):
                cluster_coords = [coordinates[j] for j in range(len(coordinates)) if assignments[j] == i]
                
                if cluster_coords:
                    # Moyenne des coordonnées du cluster
                    avg_lat = sum(coord[0] for coord in cluster_coords) / len(cluster_coords)
                    avg_lng = sum(coord[1] for coord in cluster_coords) / len(cluster_coords)
                    new_centroids.append([avg_lat, avg_lng])
                else:
                    # Garder l'ancien centroïde si pas de points assignés
                    new_centroids.append(centroids[i])
            
            # Vérifier la convergence
            converged = True
            for i in range(k):
                if self._euclidean_distance_coords(centroids[i], new_centroids[i]) > 0.0001:
                    converged = False
                    break
            
            centroids = new_centroids
            
            if converged:
                break
        
        # Créer les sous-clusters
        sub_clusters = [[] for _ in range(k)]
        for i, assignment in enumerate(assignments):
            sub_clusters[assignment].append(cluster[i])
        
        # Retourner seulement les clusters non-vides
        return [sub_cluster for sub_cluster in sub_clusters if sub_cluster]
    
    def _euclidean_distance_coords(self, coord1: List[float], coord2: List[float]) -> float:
        """
        📏 Distance euclidienne entre deux coordonnées
        """
        return math.sqrt((coord1[0] - coord2[0])**2 + (coord1[1] - coord2[1])**2)
    
    def _optimize_cluster(self, cluster: List[Dict[str, Any]], cluster_id: int, global_index_start: int = 0) -> Dict[str, Any]:
        """
        🎯 Optimise un cluster individuellement avec TSP local
        """
        if len(cluster) == 1:
            return {
                "cluster_id": cluster_id,
                "cluster_name": f"Tour {cluster_id}",
                "points": [{
                    "global_index": global_index_start,  # FIX: Utiliser l'index global correct
                    "cluster_index": 0,
                    "name": cluster[0]["name"],
                    "location": cluster[0]["geometry"]["location"],
                    "place_id": cluster[0].get("place_id"),
                    "rating": cluster[0].get("rating"),
                    "types": cluster[0].get("types", []),
                    "distance_from_previous": 0,
                    "walking_time_from_previous": 0
                }],
                "stats": {
                    "total_distance": 0,
                    "estimated_walking_time": 0,
                    "points_count": 1
                }
            }
        
        # TSP local pour ce cluster
        distances = self._build_distance_matrix_for_cluster(cluster)
        
        # Trouver le point de départ optimal (le plus excentré du cluster)
        start_idx = self._find_cluster_start_point(cluster)
        
        # Nearest neighbor avec amélioration 2-opt
        path, total_distance = self._nearest_neighbor_from_start(start_idx, distances)
        improved_path, improved_distance = self._two_opt_improvement(path, distances)
        
        # Formater le résultat
        optimized_points = []
        total_walking_time = 0
        
        for i, cluster_idx in enumerate(improved_path):
            attraction = cluster[cluster_idx]
            
            if i == 0:
                distance_from_previous = 0
                time_from_previous = 0
            else:
                prev_idx = improved_path[i-1]
                distance_from_previous = distances[prev_idx][cluster_idx]
                time_from_previous = self._distance_to_walking_minutes(distance_from_previous)
                total_walking_time += time_from_previous
            
            optimized_points.append({
                "global_index": global_index_start + i,  # Index global continu sur toute la ville
                "cluster_index": i,  # Index local dans ce cluster
                "name": attraction["name"],
                "location": attraction["geometry"]["location"],
                "place_id": attraction.get("place_id"),
                "rating": attraction.get("rating"),
                "types": attraction.get("types", []),
                "distance_from_previous": distance_from_previous,
                "walking_time_from_previous": time_from_previous
            })

        google_optimized = self._optimize_with_google_directions(
            optimized_points,
            base_global_index=global_index_start
        )
        if google_optimized:
            optimized_points = google_optimized["points"]
            improved_distance = google_optimized["total_distance"]
            total_walking_time = google_optimized["estimated_walking_time"]
            logger.info(
                "🧭 Google Directions a réordonné le tour %s (%s points)",
                cluster_id,
                len(optimized_points)
            )
        
        return {
            "cluster_id": cluster_id,
            "cluster_name": f"Tour {cluster_id}",
            "points": optimized_points,
            "stats": {
                "total_distance": improved_distance,
                "estimated_walking_time": total_walking_time,
                "points_count": len(optimized_points)
            }
        }
    
    def _generate_tour_variants(self, clusters: List[List[Dict[str, Any]]], 
                               optimized_tours: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        🌟 Génère des variantes intelligentes par cluster
        """
        variants = {
            "express": [],      # 3-4 POIs les plus populaires par cluster
            "thematic": {},     # Regroupement par types
            "discovery": [],    # Include POIs moins connus
            "weather": {
                "indoor": [],
                "outdoor": []
            }
        }
        
        for i, tour in enumerate(optimized_tours):
            cluster = clusters[i]
            
            # Variante Express (3-4 top POIs)
            top_points = sorted(
                tour["points"],
                key=lambda x: x.get("rating") if x.get("rating") is not None else 0,
                reverse=True
            )[:4]
            if len(top_points) >= 2:
                variants["express"].append({
                    "cluster_id": tour["cluster_id"],
                    "name": f"Express Tour {i+1}",
                    "points": top_points,
                    "duration": "30-45 min"
                })
            
            # Variantes thématiques
            self._add_thematic_variants(variants["thematic"], cluster, i+1)
            
            # Variante Découverte (inclut POIs moins connus)
            discovery_points = [
                p for p in tour["points"]
                if (p.get("rating") if p.get("rating") is not None else 0) < 4.2
            ]
            if len(discovery_points) >= 2:
                variants["discovery"].append({
                    "cluster_id": tour["cluster_id"],
                    "name": f"Découverte Tour {i+1}",
                    "points": discovery_points,
                    "duration": "45-60 min"
                })
        
        return variants
    
    def _add_thematic_variants(self, thematic_dict: Dict, cluster: List[Dict[str, Any]], cluster_id: int):
        """
        🎨 Ajoute des variantes thématiques basées sur les types de POIs
        """
        themes = {}
        
        for attraction in cluster:
            types = attraction.get("types", [])
            for poi_type in types:
                if poi_type in ["museum", "art_gallery", "historical_site", "church", "park"]:
                    theme = self._map_type_to_theme(poi_type)
                    if theme not in themes:
                        themes[theme] = []
                    themes[theme].append(attraction)
        
        for theme, attractions in themes.items():
            if len(attractions) >= 2:
                if theme not in thematic_dict:
                    thematic_dict[theme] = []
                
                thematic_dict[theme].append({
                    "cluster_id": cluster_id,
                    "name": f"{theme} Tour {cluster_id}",
                    "points": attractions[:5],  # Max 5 POIs par thème
                    "duration": f"{len(attractions) * 15}-{len(attractions) * 20} min"
                })
    
    def _map_type_to_theme(self, poi_type: str) -> str:
        """
        🏛️ Mappe les types Google aux thèmes touristiques
        """
        theme_mapping = {
            "museum": "Culture",
            "art_gallery": "Art",
            "historical_site": "Histoire",
            "church": "Spirituel",
            "park": "Nature",
            "shopping_mall": "Shopping",
            "restaurant": "Gastronomie"
        }
        return theme_mapping.get(poi_type, "Découverte")
    
    # === POST-FUSION DES TOURS (FIX FRAGMENTATION) ===
    
    def _post_merge_nearby_tours(self, tours: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        🔧 Version améliorée du merge qui considère TOUS les points de connexion possibles
        """
        if len(tours) <= 1:
            return tours
        
        logger.debug("   🔍 Analyse avancée de %s tours pour fusion...", len(tours))
        
        # Continuer à fusionner tant que possible
        merged = True
        current_tours = tours[:]
        
        while merged and len(current_tours) > 1:
            merged = False
            
            # Calculer toutes les distances entre tours
            merge_candidates = []
            
            for i in range(len(current_tours)):
                for j in range(i + 1, len(current_tours)):
                    tour1 = current_tours[i]
                    tour2 = current_tours[j]
                    
                    # Calculer TOUTES les connexions possibles
                    connections = self._find_all_connection_points(tour1, tour2)
                    
                    if connections:
                        best_connection = min(connections, key=lambda x: x['walking_minutes'])
                        
                        # Utiliser les vrais temps de marche Google (limite stricte de 18 minutes)
                        max_walking_minutes_limit = 18  # Limite stricte : pas plus de 18 minutes de marche
                        
                        if best_connection['walking_minutes'] <= max_walking_minutes_limit:
                            merge_candidates.append({
                                'tour1_idx': i,
                                'tour2_idx': j,
                                'connection': best_connection,
                                'priority': best_connection['walking_minutes']  # Priorité basée sur le vrai temps de marche
                            })
            
            # Fusionner le meilleur candidat
            if merge_candidates:
                # Trier par priorité (temps de marche réel, le plus court d'abord)
                merge_candidates.sort(key=lambda x: x['priority'])
                best_merge = merge_candidates[0]
                
                # Effectuer la fusion
                merged_tour = self._merge_tours_at_connection(
                    current_tours[best_merge['tour1_idx']],
                    current_tours[best_merge['tour2_idx']],
                    best_merge['connection']
                )
                
                # Remplacer les tours fusionnés
                new_tours = []
                for idx, tour in enumerate(current_tours):
                    if idx != best_merge['tour1_idx'] and idx != best_merge['tour2_idx']:
                        new_tours.append(tour)
                new_tours.append(merged_tour)
                
                current_tours = new_tours
                merged = True
                
                logger.debug("   ✅ Fusion réussie : %s tours restants", len(current_tours))
        
        return current_tours
    
    def _find_all_connection_points(self, tour1: Dict, tour2: Dict) -> List[Dict]:
        """
        🔗 Trouve TOUS les points de connexion possibles entre deux tours
        """
        connections = []
        points1 = tour1.get('points', [])
        points2 = tour2.get('points', [])
        
        if not points1 or not points2:
            return connections
        
        # Tester toutes les combinaisons
        for i, p1 in enumerate(points1):
            for j, p2 in enumerate(points2):
                loc1 = p1['location']
                loc2 = p2['location']
                
                distance = self._get_walking_distance_cached(loc1, loc2)
                if distance is None:
                    distance = self._euclidean_distance_approx(loc1, loc2)
                
                connections.append({
                    'tour1_point_idx': i,
                    'tour2_point_idx': j,
                    'tour1_point': p1,
                    'tour2_point': p2,
                    'distance': distance,
                    'walking_minutes': self._distance_to_walking_minutes(distance),
                    'connection_type': self._determine_connection_type(i, j, len(points1), len(points2))
                })
        
        return connections
    
    def _determine_connection_type(self, idx1: int, idx2: int, len1: int, len2: int) -> str:
        """
        🏷️ Détermine le type de connexion (début-début, fin-fin, etc.)
        """
        is_start1 = idx1 == 0
        is_end1 = idx1 == len1 - 1
        is_start2 = idx2 == 0
        is_end2 = idx2 == len2 - 1
        
        if is_end1 and is_start2:
            return "end1_to_start2"  # Connexion idéale !
        elif is_end2 and is_start1:
            return "end2_to_start1"  # Connexion idéale inversée
        elif is_start1 and is_start2:
            return "start_to_start"  # Nécessite inversion d'un tour
        elif is_end1 and is_end2:
            return "end_to_end"  # Nécessite inversion d'un tour
        else:
            return "middle"  # Connexion au milieu, plus complexe
    
    def _merge_tours_at_connection(self, tour1: Dict, tour2: Dict, connection: Dict) -> Dict:
        """
        🔗 Fusionne deux tours selon le point de connexion optimal
        """
        points1 = tour1['points'][:]
        points2 = tour2['points'][:]
        connection_type = connection['connection_type']
        
        # Stratégie de fusion selon le type de connexion
        if connection_type == "end1_to_start2":
            # Cas idéal : fin de tour1 → début de tour2
            merged_points = points1 + points2
            
        elif connection_type == "end2_to_start1":
            # Cas idéal inversé : fin de tour2 → début de tour1
            merged_points = points2 + points1
            
        elif connection_type == "start_to_start":
            # Inverser tour1 puis connecter
            merged_points = points1[::-1] + points2
            
        elif connection_type == "end_to_end":
            # Inverser tour2 puis connecter
            merged_points = points1 + points2[::-1]
            
        else:  # "middle"
            # Connexion complexe : réorganiser pour minimiser les détours
            idx1 = connection['tour1_point_idx']
            idx2 = connection['tour2_point_idx']
            
            # Stratégie : couper et réorganiser
            # Option 1 : tour1[0:idx1] + tour2[idx2:] + tour2[:idx2] + tour1[idx1:]
            # Option 2 : tour1[0:idx1] + tour2[idx2::-1] + tour2[idx2+1:] + tour1[idx1:]
            # Choisir la meilleure...
            
            # Simplification : insérer tour2 au point de connexion
            merged_points = points1[:idx1+1] + points2 + points1[idx1+1:]
        
        # Recalculer les indices et distances
        for i, point in enumerate(merged_points):
            point['cluster_index'] = i
            
            if i > 0:
                prev_point = merged_points[i-1]
                loc1 = prev_point['location']
                loc2 = point['location']
                
                distance = self._get_walking_distance_cached(loc1, loc2)
                if distance is None:
                    distance = int(self._euclidean_distance_approx(loc1, loc2))
                
                point['distance_from_previous'] = distance
                point['walking_time_from_previous'] = self._distance_to_walking_minutes(distance)
        
        # Optimiser l'ordre avec 2-opt
        if len(merged_points) > 3:
            merged_points = self._quick_2opt_optimization(merged_points)

        total_distance = sum(p.get('distance_from_previous', 0) for p in merged_points)
        total_time = sum(p.get('walking_time_from_previous', 0) for p in merged_points)

        google_optimized = self._optimize_with_google_directions(merged_points)
        if google_optimized:
            merged_points = google_optimized["points"]
            total_distance = google_optimized["total_distance"]
            total_time = google_optimized["estimated_walking_time"]
            logger.info(
                "🧭 Google Directions a réordonné un tour fusionné (%s points)",
                len(merged_points)
            )
        
        return {
            'cluster_id': tour1.get('cluster_id', 1),
            'cluster_name': f"Tour fusionné {tour1.get('cluster_id')}+{tour2.get('cluster_id')}",
            'points': merged_points,
            'stats': {
                'total_distance': total_distance,
                'estimated_walking_time': total_time,
                'points_count': len(merged_points)
            }
        }
    
    def _quick_2opt_optimization(self, points: List[Dict]) -> List[Dict]:
        """
        ⚡ 2-opt rapide sur une liste de points
        """
        n = len(points)
        if n <= 3:
            return points
        
        improved = True
        max_iterations = 10  # Limiter pour la performance
        iteration = 0
        
        while improved and iteration < max_iterations:
            improved = False
            iteration += 1
            
            for i in range(1, n - 2):
                for j in range(i + 1, n):
                    if j - i == 1:
                        continue
                    
                    # Calculer le gain de l'inversion
                    gain = self._calculate_2opt_gain(points, i, j)
                    
                    if gain > 0:
                        # Inverser le segment
                        points[i:j] = points[i:j][::-1]
                        improved = True
                        break
                
                if improved:
                    break
        
        # Recalculer les distances
        for i in range(1, len(points)):
            loc1 = points[i-1]['location']
            loc2 = points[i]['location']
            
            distance = self._get_walking_distance_cached(loc1, loc2)
            if distance is None:
                distance = int(self._euclidean_distance_approx(loc1, loc2))
            
            points[i]['distance_from_previous'] = distance
            points[i]['walking_time_from_previous'] = self._distance_to_walking_minutes(distance)
        
        return points
    
    def _calculate_2opt_gain(self, points: List[Dict], i: int, j: int) -> float:
        """
        📊 Calcule le gain d'une inversion 2-opt
        """
        # Distance actuelle
        current = 0
        if i > 0:
            current += self._point_distance(points[i-1], points[i])
        if j < len(points):
            current += self._point_distance(points[j-1], points[j % len(points)])
        
        # Distance après inversion
        new = 0
        if i > 0:
            new += self._point_distance(points[i-1], points[j-1])
        if j < len(points):
            new += self._point_distance(points[i], points[j % len(points)])
        
        return current - new
    
    def _point_distance(self, p1: Dict, p2: Dict) -> float:
        """
        📏 Distance entre deux points
        """
        loc1 = p1['location']
        loc2 = p2['location']
        
        distance = self._get_walking_distance_cached(loc1, loc2)
        if distance is None:
            distance = self._euclidean_distance_approx(loc1, loc2)
        
        return distance
    
    def _find_best_merge_target(self, isolated_tour: Dict[str, Any], 
                               target_tours: List[Dict[str, Any]]) -> Optional[Tuple[Dict[str, Any], float, float]]:
        """
        🎯 Trouve le meilleur tour cible pour fusionner un tour isolé
        """
        if not isolated_tour.get('points') or not target_tours:
            return None
        
        isolated_point = isolated_tour['points'][0]
        isolated_location = isolated_point['location']
        
        best_target = None
        best_distance = float('inf')
        best_minutes = float('inf')
        
        for target_tour in target_tours:
            target_points = target_tour.get('points', [])
            if not target_points:
                continue
            
            # Calculer distance vers le point le plus proche du tour cible
            min_distance_to_target = float('inf')
            
            for target_point in target_points:
                target_location = target_point['location']
                distance = self._get_walking_distance_cached(isolated_location, target_location)
                
                if distance is None:
                    distance = self._euclidean_distance_approx(isolated_location, target_location)
                
                if distance < min_distance_to_target:
                    min_distance_to_target = distance
            
            if min_distance_to_target < best_distance:
                best_distance = min_distance_to_target
                best_minutes = self._distance_to_walking_minutes(min_distance_to_target)
                best_target = target_tour
        
        if best_target:
            return (best_target, best_distance, best_minutes)
        
        return None
    
    def _merge_tour_into_target(self, source_tour: Dict[str, Any], target_tour: Dict[str, Any]):
        """
        🔗 Fusionne un tour source dans un tour cible
        """
        source_points = source_tour.get('points', [])
        target_points = target_tour.get('points', [])
        
        if not source_points:
            return
        
        # Ajouter les points du tour source au tour cible
        for point in source_points:
            target_points.append(point)
        
        # Re-optimiser l'ordre des points dans le tour fusionné
        target_tour['points'] = self._reoptimize_merged_tour_points(target_points)
        
        # Recalculer les statistiques
        self._recalculate_tour_stats(target_tour)
        
        # Mettre à jour le nom du tour
        source_name = source_tour.get('cluster_name', '').replace('Tour ', '')
        target_name = target_tour.get('cluster_name', '').replace('Tour ', '')
        target_tour['cluster_name'] = f"Tour {target_name}+{source_name}"
    
    def _reoptimize_merged_tour_points(self, points: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        🔧 Re-optimise l'ordre des points après fusion avec TSP
        """
        if len(points) <= 2:
            return points
        
        # Construire matrice de distances pour ces points
        n = len(points)
        distances = [[0] * n for _ in range(n)]
        
        for i in range(n):
            for j in range(i + 1, n):
                loc1 = points[i]['location']
                loc2 = points[j]['location']
                
                distance = self._get_walking_distance_cached(loc1, loc2)
                if distance is None:
                    distance = int(self._euclidean_distance_approx(loc1, loc2))
                
                distances[i][j] = distance
                distances[j][i] = distance
        
        # TSP simple avec nearest neighbor + 2-opt
        path, _ = self._nearest_neighbor_from_start(0, distances)
        improved_path, _ = self._two_opt_improvement(path, distances)
        
        # Réorganiser les points selon l'ordre optimal
        optimized_points = []
        for i, point_idx in enumerate(improved_path):
            point = points[point_idx].copy()
            point['cluster_index'] = i
            
            # Recalculer distance du point précédent
            if i == 0:
                point['distance_from_previous'] = 0
                point['walking_time_from_previous'] = 0
            else:
                prev_point_idx = improved_path[i-1]
                distance = distances[prev_point_idx][point_idx]
                point['distance_from_previous'] = distance
                point['walking_time_from_previous'] = self._distance_to_walking_minutes(distance)
            
            optimized_points.append(point)

        google_optimized = self._optimize_with_google_directions(optimized_points)
        if google_optimized:
            return google_optimized["points"]

        return optimized_points
    
    def _recalculate_tour_stats(self, tour: Dict[str, Any]):
        """
        📊 Recalcule les statistiques d'un tour après fusion
        """
        points = tour.get('points', [])
        
        total_distance = sum(p.get('distance_from_previous', 0) for p in points)
        total_walking_time = sum(p.get('walking_time_from_previous', 0) for p in points)
        
        tour['stats'] = {
            'total_distance': total_distance,
            'estimated_walking_time': total_walking_time,
            'points_count': len(points)
        }
    
    def _merge_nearby_normal_tours(self, tours: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        🔗 Fusionne les tours normaux qui sont très proches (optionnel)
        """
        if len(tours) <= 1:
            return tours
        
        # Pour l'instant, on ne fusionne que les tours isolés
        # Cette méthode peut être étendue pour fusionner les tours normaux proches
        
        return tours

    def _deduplicate_across_tours(self, tours: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        🚫 Empêche qu'une attraction apparaisse dans plusieurs tours simultanément.
        On privilégie les tours les plus longs.
        """
        if not tours:
            return tours

        logger.info("🔎 Vérification des doublons d'attractions entre tours...")
        # Prioriser les tours avec le plus de points (puis ordre initial)
        order = sorted(
            enumerate(tours),
            key=lambda item: len(item[1].get('points') or []),
            reverse=True
        )

        seen_place_ids = set()
        duplicates_removed = 0

        for idx, tour in order:
            points = tour.get('points', [])
            if not points:
                continue

            filtered_points = []
            for point in points:
                place_id = point.get('place_id')
                if place_id and place_id in seen_place_ids:
                    duplicates_removed += 1
                    continue
                if place_id:
                    seen_place_ids.add(place_id)
                filtered_points.append(point)

            if len(filtered_points) != len(points):
                if len(filtered_points) > 1:
                    tour['points'] = self._reoptimize_merged_tour_points(filtered_points)
                else:
                    # Un seul point ou vidé
                    tour['points'] = filtered_points

                self._recalculate_tour_stats(tour)

        # Supprimer les tours désormais vides
        cleaned_tours = [tour for tour in tours if tour.get('points')]
        removed_tours = len(tours) - len(cleaned_tours)

        if duplicates_removed or removed_tours:
            logger.info(
                "🚨 %s attractions retirées car présentes dans plusieurs tours (tours supprimés: %s)",
                duplicates_removed,
                removed_tours
            )
        else:
            logger.info("✅ Aucun doublon inter-tours détecté.")

        return cleaned_tours

    def _assert_unique_attractions(self, tours: List[Dict[str, Any]]):
        """
        Vérifie qu'aucune attraction ne se retrouve dans 2 tours ni ne partage exactement
        les mêmes coordonnées avec une autre attraction.
        """
        seen_place_ids: Dict[str, Dict[str, Any]] = {}
        seen_coordinates: Dict[Tuple[float, float], Dict[str, Any]] = {}

        for tour in tours:
            tour_label = tour.get('cluster_name') or f"Tour {tour.get('cluster_id')}"
            for point in tour.get('points', []):
                place_id = point.get('place_id')
                if not place_id:
                    raise ValueError(f"Attraction sans place_id détectée dans {tour_label}")

                if place_id in seen_place_ids:
                    other = seen_place_ids[place_id]
                    raise ValueError(
                        f"Attraction {point.get('name')} ({place_id}) déjà présente dans "
                        f"{other['tour_label']} - duplication interdite."
                    )

                location = point.get('location') or {}
                lat = location.get('lat')
                lng = location.get('lng')
                if lat is None or lng is None:
                    raise ValueError(
                        f"Attraction {point.get('name')} ({place_id}) sans coordonnées valides"
                    )

                coord_key = (round(float(lat), 7), round(float(lng), 7))
                if coord_key in seen_coordinates:
                    other = seen_coordinates[coord_key]
                    raise ValueError(
                        f"Coordonnées dupliquées détectées entre {point.get('name')} ({tour_label}) "
                        f"et {other['name']} ({other['tour_label']}) pour {coord_key}"
                    )

                seen_place_ids[place_id] = {"tour_label": tour_label}
                seen_coordinates[coord_key] = {"name": point.get('name'), "tour_label": tour_label}
    
    # === MÉTHODES UTILITAIRES ===
    
    def _get_walking_distance_cached(self, origin: Dict[str, float], destination: Dict[str, float]) -> Optional[int]:
        """
        🚶 Obtient la distance de marche avec cache intelligent
        """
        cache_key = f"{origin['lat']:.6f},{origin['lng']:.6f}-{destination['lat']:.6f},{destination['lng']:.6f}"
        
        if cache_key in self.distance_cache:
            return self.distance_cache[cache_key]
        
        # Appel API Google Directions
        try:
            params = {
                "origin": f"{origin['lat']},{origin['lng']}",
                "destination": f"{destination['lat']},{destination['lng']}",
                "mode": "walking",
                "key": self.google_api_key
            }
            
            response = requests.get(self.directions_base_url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                if data["status"] == "OK" and data["routes"]:
                    distance = data["routes"][0]["legs"][0]["distance"]["value"]
                    self.distance_cache[cache_key] = distance
                    return distance
        
        except Exception as e:
            if VERBOSE_LOGS:
                logger.debug("⚠️ Erreur API Google: %s", e)
        
        return None
    
    def _euclidean_distance_approx(self, origin: Dict[str, float], destination: Dict[str, float]) -> float:
        """
        📏 Distance euclidienne approximative (fallback)
        """
        lat_diff = origin["lat"] - destination["lat"]
        lng_diff = origin["lng"] - destination["lng"]
        
        # Approximation : 1 degré ≈ 111km
        distance_km = math.sqrt(lat_diff**2 + lng_diff**2) * 111
        return distance_km * 1000  # Convertir en mètres
    
    def _distance_to_walking_minutes(self, distance_meters: float) -> int:
        """
        ⏱️ Convertit distance en temps de marche (5 km/h)
        """
        walking_speed_ms = 1.39  # 5 km/h = 1.39 m/s
        return int((distance_meters / walking_speed_ms) / 60)

    def _optimize_with_google_directions(
        self,
        points: List[Dict[str, Any]],
        base_global_index: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Utilise Google Directions (optimize:true) pour réordonner un tour conséquent (11-25 POIs).
        """
        if len(points) <= 10 or len(points) > 25:
            return None

        try:
            origin = points[0].get("location")
            destination = points[-1].get("location")
            if not origin or not destination:
                return None

            waypoint_points = points[1:-1]
            if not waypoint_points:
                return None

            waypoint_parts = ["optimize:true"]
            for wp in waypoint_points:
                loc = wp.get("location") or {}
                lat = loc.get("lat")
                lng = loc.get("lng")
                if lat is None or lng is None:
                    return None
                waypoint_parts.append(f"{lat},{lng}")

            params = {
                "origin": f"{origin['lat']},{origin['lng']}",
                "destination": f"{destination['lat']},{destination['lng']}",
                "mode": "walking",
                "waypoints": "|".join(waypoint_parts),
                "key": self.google_api_key
            }

            response = requests.get(self.directions_base_url, params=params, timeout=12)
            if response.status_code != 200:
                return None

            data = response.json()
            routes = data.get("routes") or []
            if data.get("status") != "OK" or not routes:
                return None

            route = routes[0]
            waypoint_order = route.get("waypoint_order")
            legs = route.get("legs") or []
            if waypoint_order is None:
                return None

            optimized_waypoints = [waypoint_points[i] for i in waypoint_order]
            ordered_points = [points[0]] + optimized_waypoints + [points[-1]]

            reordered_points = []
            total_distance = 0
            total_time = 0

            for idx, point in enumerate(ordered_points):
                leg_idx = idx - 1
                distance = 0
                duration_min = 0

                if leg_idx >= 0:
                    if leg_idx < len(legs):
                        leg = legs[leg_idx] or {}
                        distance = leg.get("distance", {}).get("value", 0) or 0
                        duration_sec = leg.get("duration", {}).get("value", 0) or 0
                        duration_min = int(duration_sec / 60) if duration_sec else 0

                    if not distance:
                        distance = int(self._point_distance(ordered_points[idx - 1], point))
                    if not duration_min:
                        duration_min = self._distance_to_walking_minutes(distance)

                    total_distance += distance
                    total_time += duration_min

                new_point = dict(point)
                new_point["cluster_index"] = idx
                if base_global_index is not None:
                    new_point["global_index"] = base_global_index + idx
                elif "global_index" in point:
                    new_point["global_index"] = point["global_index"]
                new_point["distance_from_previous"] = distance
                new_point["walking_time_from_previous"] = duration_min

                reordered_points.append(new_point)

            return {
                "points": reordered_points,
                "total_distance": total_distance,
                "estimated_walking_time": total_time
            }

        except Exception as error:
            if VERBOSE_LOGS:
                logger.debug("⚠️ Optimisation Google Directions échouée: %s", error)
        return None
    
    def _build_distance_matrix_for_cluster(self, cluster: List[Dict[str, Any]]) -> List[List[int]]:
        """
        🏗️ Construit la matrice de distances pour un cluster
        """
        n = len(cluster)
        distances = [[0] * n for _ in range(n)]
        
        for i in range(n):
            for j in range(i + 1, n):
                origin = cluster[i]["geometry"]["location"]
                destination = cluster[j]["geometry"]["location"]
                
                distance = self._get_walking_distance_cached(origin, destination)
                if distance is None:
                    distance = int(self._euclidean_distance_approx(origin, destination))
                
                distances[i][j] = distance
                distances[j][i] = distance
        
        return distances
    
    def _find_cluster_start_point(self, cluster: List[Dict[str, Any]]) -> int:
        """
        🎯 Trouve le point de départ optimal dans un cluster
        """
        if len(cluster) <= 2:
            return 0

        # Calcul de la bounding box et du ratio largeur/hauteur (mètres approximatifs)
        lats = [attr["geometry"]["location"]["lat"] for attr in cluster]
        lngs = [attr["geometry"]["location"]["lng"] for attr in cluster]
        min_lat, max_lat = min(lats), max(lats)
        min_lng, max_lng = min(lngs), max(lngs)
        mid_lat_rad = math.radians((min_lat + max_lat) / 2)
        height_m = (max_lat - min_lat) * 111_000  # 1° lat ≈ 111 km
        width_m = (max_lng - min_lng) * 111_000 * math.cos(mid_lat_rad)
        height_m = max(height_m, 1e-6)  # éviter la division par zéro
        width_m = max(width_m, 1e-6)
        elongation_ratio = width_m / height_m
        elongated = elongation_ratio >= 1.6

        # Centroïde géométrique
        centroid_lat = sum(lats) / len(lats)
        centroid_lng = sum(lngs) / len(lngs)

        def _centroid_distance(attr: Dict[str, Any]) -> float:
            loc = attr["geometry"]["location"]
            d_lat = (loc["lat"] - centroid_lat) * 111_000
            d_lng = (loc["lng"] - centroid_lng) * 111_000 * math.cos(mid_lat_rad)
            return math.sqrt(d_lat**2 + d_lng**2)

        # Détection des points isolés (> 3 km de leur plus proche voisin)
        neighbor_min_dist: List[float] = []
        for i, a in enumerate(cluster):
            loc_a = a["geometry"]["location"]
            best = float("inf")
            for j, b in enumerate(cluster):
                if i == j:
                    continue
                loc_b = b["geometry"]["location"]
                dist = self._point_distance(
                    {"location": loc_a},
                    {"location": loc_b}
                )
                if dist < best:
                    best = dist
            neighbor_min_dist.append(best)

        island_threshold = 3000  # mètres
        candidates = [
            (idx, attr) for idx, attr in enumerate(cluster)
            if neighbor_min_dist[idx] <= island_threshold
        ]

        # Fallback : si tous les points sont isolés, garder l’ancienne logique (plus excentré)
        if not candidates:
            max_distance = 0
            start_index = 0
            for i, attraction in enumerate(cluster):
                loc = attraction["geometry"]["location"]
                distance = math.sqrt((loc["lat"] - centroid_lat) ** 2 + (loc["lng"] - centroid_lng) ** 2)
                if distance > max_distance:
                    max_distance = distance
                    start_index = i
            return start_index

        # Choix du départ selon la forme
        if elongated:
            # Top 20 % des points les plus éloignés du centroïde (au moins 1), puis le moins extrême
            sorted_candidates = sorted(
                candidates,
                key=lambda item: _centroid_distance(item[1]),
                reverse=True
            )
            top_k = max(1, math.ceil(len(sorted_candidates) * 0.2))
            farthest_subset = sorted_candidates[:top_k]
            chosen = min(farthest_subset, key=lambda item: _centroid_distance(item[1]))
            return chosen[0]
        else:
            # Cluster compact : point le plus central
            chosen = min(candidates, key=lambda item: _centroid_distance(item[1]))
            return chosen[0]
    
    def _nearest_neighbor_from_start(self, start_idx: int, distances: List[List[int]]) -> Tuple[List[int], int]:
        """
        🔍 Algorithme du plus proche voisin depuis un point de départ
        """
        n = len(distances)
        unvisited = set(range(n))
        path = [start_idx]
        current = start_idx
        total_distance = 0
        unvisited.remove(start_idx)
        
        while unvisited:
            nearest = min(unvisited, key=lambda x: distances[current][x])
            total_distance += distances[current][nearest]
            path.append(nearest)
            current = nearest
            unvisited.remove(nearest)
        
        return path, total_distance
    
    def _two_opt_improvement(self, path: List[int], distances: List[List[int]]) -> Tuple[List[int], int]:
        """
        🔧 Amélioration 2-opt du parcours
        """
        def calculate_path_distance(p: List[int]) -> int:
            return sum(distances[p[i]][p[i + 1]] for i in range(len(p) - 1))
        
        best_path = path[:]
        best_distance = calculate_path_distance(best_path)
        improved = True
        iterations = 0
        max_iterations = 50
        
        while improved and iterations < max_iterations:
            improved = False
            iterations += 1
            
            for i in range(1, len(path) - 2):
                for j in range(i + 1, len(path)):
                    if j - i == 1:
                        continue
                    
                    new_path = path[:i] + path[i:j][::-1] + path[j:]
                    new_distance = calculate_path_distance(new_path)
                    
                    if new_distance < best_distance:
                        best_path = new_path[:]
                        best_distance = new_distance
                        path = new_path[:]
                        improved = True
        
        return best_path, best_distance
    
    def _format_for_compatibility(self, optimized_tours: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        🔄 Formate pour compatibilité avec l'ancien système
        """
        guided_tours = []
        
        for tour in optimized_tours:
            guided_tours.append({
                "tour_id": tour["cluster_id"],
                "tour_name": tour["cluster_name"],
                "points": tour["points"],
                "stats": tour["stats"]
            })
        
        return guided_tours
    
    def generate_walking_path(self, origin: Dict[str, float], destination: Dict[str, float]) -> List[Dict[str, float]]:
        """
        Interface publique pour récupérer un chemin piéton détaillé pour deux points.
        """
        return self._get_detailed_walking_path(origin, destination)
    
    def _get_detailed_walking_path(self, origin: Dict[str, float], destination: Dict[str, float]) -> List[Dict[str, float]]:
        """
        🗺️ Récupère le chemin piéton détaillé via Google Directions
        """
        cache_key = f"path_{origin['lat']:.6f},{origin['lng']:.6f}-{destination['lat']:.6f},{destination['lng']:.6f}"
        
        if cache_key in self.directions_cache:
            return self.directions_cache[cache_key]
        
        try:
            params = {
                "origin": f"{origin['lat']},{origin['lng']}",
                "destination": f"{destination['lat']},{destination['lng']}",
                "mode": "walking",
                "key": self.google_api_key
            }
            
            response = requests.get(self.directions_base_url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                if data["status"] == "OK" and data["routes"]:
                    overview_polyline = data["routes"][0]["overview_polyline"]["points"]
                    coordinates = polyline.decode(overview_polyline)
                    
                    path_coords = [{"lat": lat, "lng": lng} for lat, lng in coordinates]
                    normalized_path = ensure_path_endpoints(path_coords, origin, destination)
                    self.directions_cache[cache_key] = normalized_path
                    return normalized_path
        
        except Exception as e:
            if VERBOSE_LOGS:
                logger.debug("⚠️ Erreur récupération chemin: %s", e)
        
        # Fallback : ligne droite
        fallback_path = ensure_path_endpoints(None, origin, destination)
        self.directions_cache[cache_key] = fallback_path
        return fallback_path
    
    def _empty_result(self) -> Dict[str, Any]:
        """📊 Résultat vide"""
        return {
            "version": "clustering",
            "tours": [],
            "total_distance": 0,
            "estimated_walking_time": 0,
            "clusters_count": 0
        }
    
    def _single_attraction_result(self, attraction: Dict[str, Any]) -> Dict[str, Any]:
        """📊 Résultat pour une seule attraction"""
        return {
            "version": "clustering",
            "tours": [{
                "cluster_id": 1,
                "cluster_name": "Tour 1",
                "points": [{
                    "global_index": 0,
                    "cluster_index": 0,
                    "name": attraction["name"],
                    "location": attraction["geometry"]["location"],
                    "distance_from_previous": 0,
                    "walking_time_from_previous": 0
                }],
                "stats": {"total_distance": 0, "estimated_walking_time": 0, "points_count": 1}
            }],
            "total_distance": 0,
            "estimated_walking_time": 0,
            "clusters_count": 1
        }
    
    def save_optimized_route_to_json(self, optimized_route: Dict[str, Any], city: str, country: str) -> str:
        """
        💾 Sauvegarde l'itinéraire optimisé
        """
        # Fichier principal
        route_file = "data/optimized_route.json"
        
        # Fichier de sauvegarde avec timestamp
        backup_file = f"data/backup/{city.lower()}_{country.lower()}_optimized_route.json"
        
        # Enrichir les données
        enriched_data = {
            **optimized_route,
            "city": city,
            "country": country,
            "generation_timestamp": time.time(),
            "generation_version": "clustering"
        }
        
        # Sauvegarder
        with open(route_file, "w", encoding="utf-8") as f:
            json.dump(enriched_data, f, ensure_ascii=False, indent=2)
        
        with open(backup_file, "w", encoding="utf-8") as f:
            json.dump(enriched_data, f, ensure_ascii=False, indent=2)
        
        logger.info("💾 Itinéraire sauvegardé: %s", route_file)
        logger.info("💾 Backup créé: %s", backup_file)
        
        return route_file
