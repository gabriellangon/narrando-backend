"""
🔍 Diagnostic V2 - Analyser les décisions de clustering et TSP
Outil de transparence pour comprendre pourquoi l'algorithme V2 fait ses choix
"""
import json
import math
import os
import time
from typing import List, Dict, Any, Tuple
from datetime import datetime

class RouteOptimizerV2Diagnostic:
    """
    🔬 Outil de diagnostic pour analyser les décisions de l'algorithme V2
    """
    
    def __init__(self, max_walking_minutes: int = 15):
        self.max_walking_minutes = max_walking_minutes
        self.max_walking_distance = max_walking_minutes * 60 * 1.39  # 15min = 1251m
        self.diagnostic_log = []
        
    def analyze_clustering_decisions(self, attractions: List[Dict[str, Any]], 
                                   result_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        🧠 Analyse complète des décisions de clustering
        """
        print("🔍 === DIAGNOSTIC V2 EN COURS ===")
        
        analysis = {
            "timestamp": datetime.now().isoformat(),
            "input_data": {
                "attractions_count": len(attractions),
                "constraint_max_walking_minutes": self.max_walking_minutes,
                "constraint_max_walking_distance": self.max_walking_distance
            },
            "clustering_analysis": {},
            "decision_trace": [],
            "recommendations": [],
            "visual_data": {}
        }
        
        if len(attractions) <= 1:
            analysis["decision_trace"].append({
                "step": "early_exit",
                "reason": "Pas assez d'attractions pour clustering",
                "attractions_count": len(attractions)
            })
            return analysis
        
        # 1. Analyse de la matrice de distances
        print("🔄 Analyse des distances entre attractions...")
        distance_analysis = self._analyze_distance_matrix(attractions)
        analysis["clustering_analysis"]["distance_matrix"] = distance_analysis
        
        # 2. Simulation du clustering
        print("📦 Simulation du processus de clustering...")
        clustering_trace = self._simulate_clustering_process(attractions)
        analysis["clustering_analysis"]["clustering_trace"] = clustering_trace
        
        # 3. Analyse des résultats
        if result_data:
            result_analysis = self._analyze_clustering_results(attractions, result_data)
            analysis["clustering_analysis"]["results_analysis"] = result_analysis
        
        # 4. Recommandations d'amélioration
        recommendations = self._generate_recommendations(analysis)
        analysis["recommendations"] = recommendations
        
        # 5. Données pour visualisation
        visual_data = self._prepare_visual_data(attractions, analysis)
        analysis["visual_data"] = visual_data
        
        print("✅ Diagnostic terminé !")
        return analysis
    
    def _analyze_distance_matrix(self, attractions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        📊 Analyse détaillée de la matrice de distances
        """
        n = len(attractions)
        distances = []
        connections_within_constraint = []
        
        # Calculer toutes les distances
        for i in range(n):
            for j in range(i + 1, n):
                origin = attractions[i]["geometry"]["location"]
                destination = attractions[j]["geometry"]["location"]
                
                # Distance euclidienne approximative (comme fallback dans V2)
                distance = self._euclidean_distance_approx(origin, destination)
                
                distances.append({
                    "from_index": i,
                    "to_index": j,
                    "from_name": attractions[i]["name"][:30] + "...",
                    "to_name": attractions[j]["name"][:30] + "...",
                    "distance_meters": round(distance, 0),
                    "walking_minutes": round(distance / (1.39 * 60), 1),
                    "within_constraint": distance <= self.max_walking_distance
                })
                
                if distance <= self.max_walking_distance:
                    connections_within_constraint.append((i, j))
        
        # Statistiques
        all_distances = [d["distance_meters"] for d in distances]
        within_constraint_count = len([d for d in distances if d["within_constraint"]])
        
        return {
            "total_pairs": len(distances),
            "connections_within_constraint": within_constraint_count,
            "connectivity_ratio": round(within_constraint_count / len(distances) * 100, 1),
            "distance_stats": {
                "min_distance": min(all_distances),
                "max_distance": max(all_distances),
                "avg_distance": round(sum(all_distances) / len(all_distances), 0),
                "median_distance": sorted(all_distances)[len(all_distances) // 2]
            },
            "all_distances": sorted(distances, key=lambda x: x["distance_meters"]),
            "connections_list": connections_within_constraint
        }
    
    def _simulate_clustering_process(self, attractions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        🎭 Simule étape par étape le processus de clustering
        """
        trace = []
        n = len(attractions)
        
        # Étape 1 : Construction de la matrice binaire
        trace.append({
            "step": 1,
            "name": "Construction matrice binaire",
            "description": f"Conversion des distances en connexions binaires (≤{self.max_walking_minutes}min)"
        })
        
        # Construire la matrice d'adjacence
        adjacency_matrix = [[0] * n for _ in range(n)]
        connections_details = []
        
        for i in range(n):
            for j in range(n):
                if i == j:
                    adjacency_matrix[i][j] = 1
                else:
                    origin = attractions[i]["geometry"]["location"]
                    destination = attractions[j]["geometry"]["location"]
                    distance = self._euclidean_distance_approx(origin, destination)
                    
                    if distance <= self.max_walking_distance:
                        adjacency_matrix[i][j] = 1
                        if i < j:  # Éviter les doublons
                            connections_details.append({
                                "attraction_1": attractions[i]["name"][:30] + "...",
                                "attraction_2": attractions[j]["name"][:30] + "...",
                                "distance_meters": round(distance, 0),
                                "connected": True
                            })
        
        trace.append({
            "step": 2,
            "name": "Matrice d'adjacence créée",
            "description": f"Matrice {n}x{n} avec {len(connections_details)} connexions",
            "adjacency_matrix": adjacency_matrix,
            "connections_details": connections_details
        })
        
        # Étape 2 : Clustering par composantes connexes
        trace.append({
            "step": 3,
            "name": "Clustering par composantes connexes",
            "description": "Regroupement des attractions connectées"
        })
        
        visited = [False] * n
        clusters = []
        cluster_details = []
        
        def dfs(node: int, cluster: List[int], cluster_id: int):
            visited[node] = True
            cluster.append(node)
            
            connections = []
            for neighbor in range(n):
                if adjacency_matrix[node][neighbor] and not visited[neighbor]:
                    connections.append(neighbor)
                    dfs(neighbor, cluster, cluster_id)
            
            return connections
        
        cluster_id = 1
        for i in range(n):
            if not visited[i]:
                cluster_indices = []
                dfs(i, cluster_indices, cluster_id)
                
                cluster_attractions = [attractions[idx] for idx in cluster_indices]
                clusters.append(cluster_attractions)
                
                cluster_details.append({
                    "cluster_id": cluster_id,
                    "size": len(cluster_indices),
                    "attraction_indices": cluster_indices,
                    "attraction_names": [attractions[idx]["name"][:30] + "..." for idx in cluster_indices],
                    "centroid": self._calculate_cluster_centroid(cluster_attractions)
                })
                
                cluster_id += 1
        
        trace.append({
            "step": 4,
            "name": "Clusters initiaux créés",
            "description": f"{len(clusters)} clusters trouvés par composantes connexes",
            "clusters": cluster_details
        })
        
        # Étape 3 : Division des gros clusters
        final_clusters = []
        split_operations = []
        
        for i, cluster in enumerate(clusters):
            if len(cluster) <= 8:
                final_clusters.append(cluster)
                split_operations.append({
                    "original_cluster_id": i + 1,
                    "action": "kept_as_is",
                    "size": len(cluster),
                    "reason": "Taille acceptable (≤8 POIs)"
                })
            else:
                sub_clusters = self._split_large_cluster_diagnostic(cluster)
                final_clusters.extend(sub_clusters)
                
                split_operations.append({
                    "original_cluster_id": i + 1,
                    "action": "split",
                    "original_size": len(cluster),
                    "resulting_clusters": len(sub_clusters),
                    "new_sizes": [len(sc) for sc in sub_clusters],
                    "reason": f"Trop grand ({len(cluster)} POIs > 8)"
                })
        
        trace.append({
            "step": 5,
            "name": "Division des gros clusters",
            "description": "Subdivision des clusters trop volumineux",
            "split_operations": split_operations,
            "final_clusters_count": len(final_clusters)
        })
        
        return trace
    
    def _split_large_cluster_diagnostic(self, cluster: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        """
        ✂️ Version diagnostic de la division des gros clusters
        """
        if len(cluster) <= 8:
            return [cluster]
        
        coordinates = [
            [attr["geometry"]["location"]["lat"], attr["geometry"]["location"]["lng"]]
            for attr in cluster
        ]
        
        n_clusters = min(3, len(cluster) // 5)
        
        # K-means simplifié (même logique que V2)
        sub_clusters = self._simple_kmeans_clustering_diagnostic(cluster, coordinates, n_clusters)
        
        return sub_clusters
    
    def _simple_kmeans_clustering_diagnostic(self, cluster: List[Dict[str, Any]], 
                                           coordinates: List[List[float]], k: int) -> List[List[Dict[str, Any]]]:
        """
        🧠 K-means diagnostic avec traces
        """
        if k >= len(cluster):
            return [[attr] for attr in cluster]
        
        import random
        random.seed(42)  # Même seed que V2
        
        n_points = len(coordinates)
        centroid_indices = random.sample(range(n_points), k)
        centroids = [coordinates[idx][:] for idx in centroid_indices]
        
        # Algorithme K-means (même logique que V2)
        for iteration in range(10):
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
            
            # Recalculer centroids
            new_centroids = []
            for i in range(k):
                cluster_coords = [coordinates[j] for j in range(len(coordinates)) if assignments[j] == i]
                
                if cluster_coords:
                    avg_lat = sum(coord[0] for coord in cluster_coords) / len(cluster_coords)
                    avg_lng = sum(coord[1] for coord in cluster_coords) / len(cluster_coords)
                    new_centroids.append([avg_lat, avg_lng])
                else:
                    new_centroids.append(centroids[i])
            
            # Vérifier convergence
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
        
        return [sub_cluster for sub_cluster in sub_clusters if sub_cluster]
    
    def _analyze_clustering_results(self, attractions: List[Dict[str, Any]], 
                                  result_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        📋 Analyse des résultats de clustering
        """
        tours = result_data.get("tours", [])
        
        analysis = {
            "tours_count": len(tours),
            "tours_details": [],
            "potential_merges": [],
            "isolation_issues": []
        }
        
        # Analyser chaque tour
        for i, tour in enumerate(tours):
            points = tour.get("points", [])
            
            # Calculer le centroïde du tour
            if points:
                avg_lat = sum(p["location"]["lat"] for p in points) / len(points)
                avg_lng = sum(p["location"]["lng"] for p in points) / len(points)
                centroid = {"lat": avg_lat, "lng": avg_lng}
            else:
                centroid = {"lat": 0, "lng": 0}
            
            tour_detail = {
                "tour_id": i + 1,
                "tour_name": tour.get("cluster_name", f"Tour {i+1}"),
                "points_count": len(points),
                "points_names": [p["name"][:30] + "..." for p in points],
                "centroid": centroid,
                "total_distance": tour.get("stats", {}).get("total_distance", 0),
                "walking_time": tour.get("stats", {}).get("estimated_walking_time", 0)
            }
            
            analysis["tours_details"].append(tour_detail)
        
        # Analyser les possibilités de fusion
        for i in range(len(tours)):
            for j in range(i + 1, len(tours)):
                tour1 = analysis["tours_details"][i]
                tour2 = analysis["tours_details"][j]
                
                # Distance entre centroids
                distance = self._euclidean_distance_approx(tour1["centroid"], tour2["centroid"])
                walking_minutes = distance / (1.39 * 60)
                
                if walking_minutes <= self.max_walking_minutes * 1.5:  # Marge de 50%
                    # Trouver les points les plus proches entre les deux tours
                    min_inter_distance = float('inf')
                    closest_points = None
                    
                    tour1_points = [p for p in tours[i]["points"]]
                    tour2_points = [p for p in tours[j]["points"]]
                    
                    for p1 in tour1_points:
                        for p2 in tour2_points:
                            d = self._euclidean_distance_approx(p1["location"], p2["location"])
                            if d < min_inter_distance:
                                min_inter_distance = d
                                closest_points = (p1["name"][:30] + "...", p2["name"][:30] + "...")
                    
                    analysis["potential_merges"].append({
                        "tour1_id": i + 1,
                        "tour2_id": j + 1,
                        "centroid_distance_m": round(distance, 0),
                        "centroid_walking_minutes": round(walking_minutes, 1),
                        "closest_points_distance_m": round(min_inter_distance, 0),
                        "closest_points_minutes": round(min_inter_distance / (1.39 * 60), 1),
                        "closest_points_names": closest_points,
                        "merge_feasible": min_inter_distance <= self.max_walking_distance,
                        "total_combined_points": tour1["points_count"] + tour2["points_count"]
                    })
        
        return analysis
    
    def _generate_recommendations(self, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        💡 Génère des recommandations d'amélioration
        """
        recommendations = []
        
        # Analyser les fusions possibles
        potential_merges = analysis.get("clustering_analysis", {}).get("results_analysis", {}).get("potential_merges", [])
        
        feasible_merges = [m for m in potential_merges if m.get("merge_feasible", False)]
        
        if feasible_merges:
            recommendations.append({
                "type": "merge_opportunity",
                "priority": "high",
                "title": "Opportunités de fusion détectées",
                "description": f"{len(feasible_merges)} paires de tours pourraient être fusionnées",
                "details": feasible_merges,
                "impact": "Réduction du nombre de tours pour une meilleure expérience utilisateur"
            })
        
        # Analyser la connectivité
        clustering_analysis = analysis.get("clustering_analysis", {})
        distance_matrix = clustering_analysis.get("distance_matrix", {})
        connectivity_ratio = distance_matrix.get("connectivity_ratio", 0)
        
        if connectivity_ratio < 30:
            recommendations.append({
                "type": "connectivity_issue",
                "priority": "medium",
                "title": "Faible connectivité détectée",
                "description": f"Seulement {connectivity_ratio}% des paires d'attractions sont connectées",
                "suggestion": "Considérer augmenter la contrainte de temps de marche ou utiliser une approche différente",
                "current_constraint": f"{self.max_walking_minutes} minutes",
                "suggested_constraint": f"{self.max_walking_minutes + 5} minutes"
            })
        
        # Analyser les clusters de taille 1
        tours_details = analysis.get("clustering_analysis", {}).get("results_analysis", {}).get("tours_details", [])
        single_point_tours = [t for t in tours_details if t.get("points_count", 0) == 1]
        
        if single_point_tours:
            recommendations.append({
                "type": "isolation_issue",
                "priority": "high",
                "title": "Tours à point unique détectés",
                "description": f"{len(single_point_tours)} tours ne contiennent qu'un seul point",
                "isolated_tours": [t["tour_name"] for t in single_point_tours],
                "suggestion": "Ces points isolés devraient être intégrés aux tours voisins"
            })
        
        return recommendations
    
    def _prepare_visual_data(self, attractions: List[Dict[str, Any]], 
                           analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        🎨 Prépare les données pour visualisation
        """
        visual_data = {
            "attractions_map": [],
            "connections_map": [],
            "tours_map": [],
            "centroid_connections": []
        }
        
        # Points des attractions avec coordonnées
        for i, attr in enumerate(attractions):
            visual_data["attractions_map"].append({
                "id": i,
                "name": attr["name"][:30] + "...",
                "lat": attr["geometry"]["location"]["lat"],
                "lng": attr["geometry"]["location"]["lng"],
                "rating": attr.get("rating", 0)
            })
        
        # Connexions dans la contrainte
        distance_analysis = analysis.get("clustering_analysis", {}).get("distance_matrix", {})
        connections = distance_analysis.get("connections_list", [])
        
        for i, j in connections:
            visual_data["connections_map"].append({
                "from": i,
                "to": j,
                "from_name": attractions[i]["name"][:20] + "...",
                "to_name": attractions[j]["name"][:20] + "...",
                "color": "green"
            })
        
        # Tours (si résultats disponibles)
        results_analysis = analysis.get("clustering_analysis", {}).get("results_analysis", {})
        tours_details = results_analysis.get("tours_details", [])
        
        colors = ["red", "blue", "purple", "orange", "yellow", "pink", "gray", "brown"]
        
        for i, tour in enumerate(tours_details):
            visual_data["tours_map"].append({
                "tour_id": tour["tour_id"],
                "name": tour["tour_name"],
                "centroid": tour["centroid"],
                "points_count": tour["points_count"],
                "color": colors[i % len(colors)]
            })
        
        return visual_data
    
    def save_diagnostic_report(self, analysis: Dict[str, Any], city: str, country: str = "") -> str:
        """
        💾 Sauvegarde le rapport de diagnostic
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"utils/diagnostic_report_{city.lower()}_{country.lower()}_{timestamp}.json"
        
        # Enrichir avec métadonnées
        report = {
            "meta": {
                "city": city,
                "country": country,
                "generated_at": datetime.now().isoformat(),
                "algorithm_version": "V2_clustering",
                "diagnostic_version": "1.0"
            },
            **analysis
        }
        
        os.makedirs("utils", exist_ok=True)
        
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        print(f"📋 Rapport diagnostic sauvegardé : {filename}")
        return filename
    
    def generate_human_readable_report(self, analysis: Dict[str, Any]) -> str:
        """
        📄 Génère un rapport lisible par l'humain
        """
        report_lines = []
        report_lines.append("🔍 === RAPPORT DIAGNOSTIC V2 ===")
        report_lines.append("")
        
        # Informations générales
        input_data = analysis.get("input_data", {})
        report_lines.append(f"📊 Données d'entrée:")
        report_lines.append(f"   • {input_data.get('attractions_count', 0)} attractions à organiser")
        report_lines.append(f"   • Contrainte: ≤ {input_data.get('constraint_max_walking_minutes', 15)} minutes de marche")
        report_lines.append(f"   • Distance max: ≤ {round(input_data.get('constraint_max_walking_distance', 0), 0)}m")
        report_lines.append("")
        
        # Analyse des distances
        clustering_analysis = analysis.get("clustering_analysis", {})
        distance_matrix = clustering_analysis.get("distance_matrix", {})
        
        if distance_matrix:
            report_lines.append("📏 Analyse des distances:")
            report_lines.append(f"   • {distance_matrix.get('total_pairs', 0)} paires d'attractions analysées")
            report_lines.append(f"   • {distance_matrix.get('connections_within_constraint', 0)} connexions dans la contrainte")
            report_lines.append(f"   • Ratio de connectivité: {distance_matrix.get('connectivity_ratio', 0)}%")
            
            stats = distance_matrix.get('distance_stats', {})
            report_lines.append(f"   • Distance min: {round(stats.get('min_distance', 0), 0)}m")
            report_lines.append(f"   • Distance max: {round(stats.get('max_distance', 0), 0)}m")
            report_lines.append(f"   • Distance moyenne: {round(stats.get('avg_distance', 0), 0)}m")
            report_lines.append("")
        
        # Résultats du clustering
        results_analysis = clustering_analysis.get("results_analysis", {})
        if results_analysis:
            report_lines.append("🎯 Résultats du clustering:")
            report_lines.append(f"   • {results_analysis.get('tours_count', 0)} tours créés")
            
            tours_details = results_analysis.get('tours_details', [])
            for tour in tours_details:
                report_lines.append(f"   • {tour.get('tour_name', 'Tour')}: {tour.get('points_count', 0)} points, "
                                  f"{round(tour.get('total_distance', 0), 0)}m, "
                                  f"{round(tour.get('walking_time', 0), 0)}min")
            report_lines.append("")
        
        # Opportunités de fusion
        potential_merges = results_analysis.get("potential_merges", [])
        if potential_merges:
            report_lines.append("🔗 Opportunités de fusion détectées:")
            for merge in potential_merges:
                status = "✅ FAISABLE" if merge.get("merge_feasible", False) else "❌ Trop loin"
                report_lines.append(f"   • Tour {merge.get('tour1_id', 0)} ↔ Tour {merge.get('tour2_id', 0)}: "
                                  f"{round(merge.get('closest_points_minutes', 0), 1)}min entre points les plus proches {status}")
            report_lines.append("")
        
        # Recommandations
        recommendations = analysis.get("recommendations", [])
        if recommendations:
            report_lines.append("💡 Recommandations:")
            for rec in recommendations:
                priority_emoji = {"high": "🔥", "medium": "⚠️", "low": "💭"}.get(rec.get("priority", "low"), "💭")
                report_lines.append(f"   {priority_emoji} {rec.get('title', 'Recommandation')}")
                report_lines.append(f"      {rec.get('description', 'Aucune description')}")
                report_lines.append("")
        
        report_lines.append("🎉 === FIN DU RAPPORT ===")
        
        return "\n".join(report_lines)
    
    # === MÉTHODES UTILITAIRES ===
    
    def _euclidean_distance_approx(self, origin: Dict[str, float], destination: Dict[str, float]) -> float:
        """📏 Distance euclidienne approximative (même logique que V2)"""
        lat_diff = origin["lat"] - destination["lat"]
        lng_diff = origin["lng"] - destination["lng"]
        distance_km = math.sqrt(lat_diff**2 + lng_diff**2) * 111
        return distance_km * 1000
    
    def _euclidean_distance_coords(self, coord1: List[float], coord2: List[float]) -> float:
        """📏 Distance euclidienne entre coordonnées"""
        return math.sqrt((coord1[0] - coord2[0])**2 + (coord1[1] - coord2[1])**2)
    
    def _calculate_cluster_centroid(self, cluster: List[Dict[str, Any]]) -> Dict[str, float]:
        """📍 Calcule le centroïde d'un cluster"""
        if not cluster:
            return {"lat": 0, "lng": 0}
        
        avg_lat = sum(attr["geometry"]["location"]["lat"] for attr in cluster) / len(cluster)
        avg_lng = sum(attr["geometry"]["location"]["lng"] for attr in cluster) / len(cluster)
        
        return {"lat": avg_lat, "lng": avg_lng}