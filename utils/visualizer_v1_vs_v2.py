"""
🎨 Visualisateur V1 vs V2 - Comparaison visuelle des résultats
"""
import json
import os
import math
from typing import Dict, Any, List, Optional

class V1vsV2Visualizer:
    """
    🔍 Comparateur visuel entre les résultats V1 et V2
    """
    
    def __init__(self):
        self.colors = ["🔴", "🔵", "🟡", "🟢", "🟣", "🟠", "🤎", "⚫"]
    
    def compare_algorithms(self, city: str, country: str = "") -> Dict[str, Any]:
        """
        📊 Compare les résultats V1 et V2 pour une ville
        """
        base_name = f"{city.lower()}_{country.lower()}" if country else city.lower()
        
        # Fichiers à comparer
        v1_file = f"data/backup/{base_name}_optimized_route.json"  # V1 original
        v2_file = f"data/backup/{base_name}_optimized_route_v2.json"  # V2 clustering
        attractions_file = f"data/backup/{base_name}_filtered_v2_attractions.json"
        
        print(f"🔍 Comparaison V1 vs V2 pour {city.title()} ({country.title()})")
        print("=" * 60)
        
        # Vérifier les fichiers
        files_status = {
            "v1_available": os.path.exists(v1_file),
            "v2_available": os.path.exists(v2_file),
            "attractions_available": os.path.exists(attractions_file)
        }
        
        print(f"📁 Disponibilité des fichiers:")
        print(f"   V1 Results: {'✅' if files_status['v1_available'] else '❌'} {v1_file}")
        print(f"   V2 Results: {'✅' if files_status['v2_available'] else '❌'} {v2_file}")
        print(f"   Attractions: {'✅' if files_status['attractions_available'] else '❌'} {attractions_file}")
        
        comparison = {
            "city": city,
            "country": country,
            "files_status": files_status,
            "v1_analysis": None,
            "v2_analysis": None,
            "comparison_metrics": {},
            "visual_comparison": {},
            "recommendations": []
        }
        
        # Charger les attractions
        if files_status["attractions_available"]:
            with open(attractions_file, "r", encoding="utf-8") as f:
                attractions_data = json.load(f)
            attractions = attractions_data.get("filtered_attractions", [])
            comparison["total_attractions"] = len(attractions)
        else:
            attractions = []
            comparison["total_attractions"] = 0
        
        # Analyser V1
        if files_status["v1_available"]:
            print(f"\\n📈 Analyse V1...")
            comparison["v1_analysis"] = self._analyze_v1_results(v1_file, attractions)
        
        # Analyser V2
        if files_status["v2_available"]:
            print(f"\\n📈 Analyse V2...")
            comparison["v2_analysis"] = self._analyze_v2_results(v2_file, attractions)
        
        # Comparaison métrique
        if comparison["v1_analysis"] and comparison["v2_analysis"]:
            print(f"\\n📊 Calcul des métriques de comparaison...")
            comparison["comparison_metrics"] = self._calculate_comparison_metrics(
                comparison["v1_analysis"], comparison["v2_analysis"]
            )
            
            # Visualisation
            print(f"\\n🎨 Génération de la visualisation...")
            comparison["visual_comparison"] = self._generate_visual_comparison(
                comparison["v1_analysis"], comparison["v2_analysis"], attractions
            )
            
            # Recommandations
            comparison["recommendations"] = self._generate_comparison_recommendations(comparison)
        
        return comparison
    
    def _analyze_v1_results(self, v1_file: str, attractions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        📊 Analyse les résultats V1
        """
        with open(v1_file, "r", encoding="utf-8") as f:
            v1_data = json.load(f)
        
        # Extraire les tours V1 (format peut varier)
        tours = v1_data.get("guided_tours", [])
        if not tours:
            tours = v1_data.get("tours", [])
        
        analysis = {
            "algorithm": "V1_original",
            "tours_count": len(tours),
            "total_points": sum(len(tour.get("points", [])) for tour in tours),
            "total_distance": v1_data.get("total_distance", 0),
            "total_walking_time": v1_data.get("estimated_walking_time", 0),
            "tours_details": []
        }
        
        for i, tour in enumerate(tours):
            points = tour.get("points", [])
            
            tour_detail = {
                "tour_id": i + 1,
                "name": tour.get("tour_name", f"Tour {i+1}"),
                "points_count": len(points),
                "points_names": [p.get("name", "Unknown")[:30] + "..." for p in points],
                "distance": tour.get("stats", {}).get("total_distance", 0) or tour.get("total_distance", 0),
                "walking_time": tour.get("stats", {}).get("estimated_walking_time", 0) or tour.get("estimated_walking_time", 0)
            }
            
            analysis["tours_details"].append(tour_detail)
        
        return analysis
    
    def _analyze_v2_results(self, v2_file: str, attractions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        📊 Analyse les résultats V2
        """
        with open(v2_file, "r", encoding="utf-8") as f:
            v2_data = json.load(f)
        
        tours = v2_data.get("tours", [])
        
        analysis = {
            "algorithm": "V2_clustering",
            "tours_count": len(tours),
            "clusters_count": v2_data.get("clusters_count", len(tours)),
            "total_points": sum(len(tour.get("points", [])) for tour in tours),
            "total_distance": v2_data.get("total_distance", 0),
            "total_walking_time": v2_data.get("estimated_walking_time", 0),
            "constraint_minutes": v2_data.get("constraint_max_walking_minutes", 15),
            "tours_details": []
        }
        
        for tour in tours:
            points = tour.get("points", [])
            
            tour_detail = {
                "cluster_id": tour.get("cluster_id", 0),
                "name": tour.get("cluster_name", "Unknown Tour"),
                "points_count": len(points),
                "points_names": [p.get("name", "Unknown")[:30] + "..." for p in points],
                "distance": tour.get("stats", {}).get("total_distance", 0),
                "walking_time": tour.get("stats", {}).get("estimated_walking_time", 0)
            }
            
            analysis["tours_details"].append(tour_detail)
        
        return analysis
    
    def _calculate_comparison_metrics(self, v1_analysis: Dict[str, Any], 
                                     v2_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        📊 Calcule les métriques de comparaison
        """
        metrics = {
            "tours_comparison": {
                "v1_tours": v1_analysis["tours_count"],
                "v2_tours": v2_analysis["tours_count"],
                "difference": v2_analysis["tours_count"] - v1_analysis["tours_count"],
                "change_percentage": round((v2_analysis["tours_count"] / v1_analysis["tours_count"] - 1) * 100, 1) if v1_analysis["tours_count"] > 0 else 0
            },
            "coverage_comparison": {
                "v1_total_points": v1_analysis["total_points"],
                "v2_total_points": v2_analysis["total_points"],
                "points_difference": v2_analysis["total_points"] - v1_analysis["total_points"]
            },
            "distance_comparison": {
                "v1_distance": v1_analysis["total_distance"],
                "v2_distance": v2_analysis["total_distance"],
                "difference_meters": v2_analysis["total_distance"] - v1_analysis["total_distance"],
                "improvement_percentage": round((v1_analysis["total_distance"] / v2_analysis["total_distance"] - 1) * 100, 1) if v2_analysis["total_distance"] > 0 else 0
            },
            "time_comparison": {
                "v1_time": v1_analysis["total_walking_time"],
                "v2_time": v2_analysis["total_walking_time"],
                "difference_minutes": v2_analysis["total_walking_time"] - v1_analysis["total_walking_time"]
            },
            "efficiency_metrics": {
                "v1_avg_points_per_tour": round(v1_analysis["total_points"] / v1_analysis["tours_count"], 1) if v1_analysis["tours_count"] > 0 else 0,
                "v2_avg_points_per_tour": round(v2_analysis["total_points"] / v2_analysis["tours_count"], 1) if v2_analysis["tours_count"] > 0 else 0,
                "v1_avg_distance_per_tour": round(v1_analysis["total_distance"] / v1_analysis["tours_count"], 0) if v1_analysis["tours_count"] > 0 else 0,
                "v2_avg_distance_per_tour": round(v2_analysis["total_distance"] / v2_analysis["tours_count"], 0) if v2_analysis["tours_count"] > 0 else 0
            }
        }
        
        # Tours isolés (1 seul point)
        v1_isolated = len([t for t in v1_analysis["tours_details"] if t["points_count"] == 1])
        v2_isolated = len([t for t in v2_analysis["tours_details"] if t["points_count"] == 1])
        
        metrics["isolation_comparison"] = {
            "v1_isolated_tours": v1_isolated,
            "v2_isolated_tours": v2_isolated,
            "isolation_increase": v2_isolated - v1_isolated
        }
        
        return metrics
    
    def _generate_visual_comparison(self, v1_analysis: Dict[str, Any], 
                                   v2_analysis: Dict[str, Any],
                                   attractions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        🎨 Génère une comparaison visuelle
        """
        visual = {
            "side_by_side_tours": [],
            "tours_size_distribution": {
                "v1": {},
                "v2": {}
            },
            "geographic_spread": {},
            "tour_efficiency": []
        }
        
        # Distribution des tailles de tours
        for analysis, key in [(v1_analysis, "v1"), (v2_analysis, "v2")]:
            size_dist = {}
            for tour in analysis["tours_details"]:
                size = tour["points_count"]
                size_dist[size] = size_dist.get(size, 0) + 1
            visual["tours_size_distribution"][key] = size_dist
        
        # Comparaison côte à côte
        max_tours = max(len(v1_analysis["tours_details"]), len(v2_analysis["tours_details"]))
        
        for i in range(max_tours):
            v1_tour = v1_analysis["tours_details"][i] if i < len(v1_analysis["tours_details"]) else None
            v2_tour = v2_analysis["tours_details"][i] if i < len(v2_analysis["tours_details"]) else None
            
            visual["side_by_side_tours"].append({
                "index": i + 1,
                "v1_tour": v1_tour,
                "v2_tour": v2_tour
            })
        
        return visual
    
    def _generate_comparison_recommendations(self, comparison: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        💡 Génère des recommandations basées sur la comparaison
        """
        recommendations = []
        metrics = comparison["comparison_metrics"]
        
        # Tours multiples vs tour unique
        tours_diff = metrics["tours_comparison"]["difference"]
        if tours_diff > 5:
            recommendations.append({
                "type": "fragmentation_issue",
                "priority": "high",
                "title": "Fragmentation excessive en V2",
                "description": f"V2 créé {tours_diff} tours de plus que V1 ({metrics['tours_comparison']['v2_tours']} vs {metrics['tours_comparison']['v1_tours']})",
                "suggestion": "Considérer assouplir la contrainte de 15min ou implémenter une post-fusion des tours proches"
            })
        
        # Tours isolés
        isolated_increase = metrics["isolation_comparison"]["isolation_increase"]
        if isolated_increase > 0:
            recommendations.append({
                "type": "isolation_increase",
                "priority": "high",
                "title": "Augmentation des tours isolés",
                "description": f"+{isolated_increase} tours à point unique en V2",
                "suggestion": "Intégrer ces points isolés aux tours voisins même si cela dépasse légèrement la contrainte"
            })
        
        # Efficacité distance
        distance_change = metrics["distance_comparison"]["improvement_percentage"]
        if distance_change > 20:
            recommendations.append({
                "type": "distance_improvement",
                "priority": "positive",
                "title": "Amélioration significative des distances",
                "description": f"V2 réduit la distance totale de {abs(distance_change)}%",
                "benefit": "Meilleure optimisation locale"
            })
        elif distance_change < -20:
            recommendations.append({
                "type": "distance_degradation",
                "priority": "medium",
                "title": "Dégradation des distances",
                "description": f"V2 augmente la distance totale de {abs(distance_change)}%",
                "suggestion": "Vérifier l'algorithme TSP local dans chaque cluster"
            })
        
        return recommendations
    
    def generate_comparison_report(self, comparison: Dict[str, Any]) -> str:
        """
        📄 Génère un rapport de comparaison lisible
        """
        lines = []
        lines.append("🔍 === COMPARAISON V1 vs V2 ===")
        lines.append("")
        
        city = comparison.get("city", "Unknown")
        country = comparison.get("country", "Unknown")
        lines.append(f"🏙️  Ville: {city.title()} ({country.title()})")
        lines.append(f"📊 Total attractions: {comparison.get('total_attractions', 0)}")
        lines.append("")
        
        # Disponibilité des données
        files_status = comparison.get("files_status", {})
        lines.append("📁 Disponibilité des données:")
        lines.append(f"   V1: {'✅ Disponible' if files_status.get('v1_available') else '❌ Manquant'}")
        lines.append(f"   V2: {'✅ Disponible' if files_status.get('v2_available') else '❌ Manquant'}")
        lines.append("")
        
        # Métriques de comparaison
        metrics = comparison.get("comparison_metrics", {})
        if metrics:
            lines.append("📊 MÉTRIQUES DE COMPARAISON")
            lines.append("=" * 40)
            
            # Tours
            tours_comp = metrics.get("tours_comparison", {})
            lines.append(f"🎯 Nombre de tours:")
            lines.append(f"   V1: {tours_comp.get('v1_tours', 0)} tours")
            lines.append(f"   V2: {tours_comp.get('v2_tours', 0)} tours")
            lines.append(f"   Différence: {tours_comp.get('difference', 0):+d} ({tours_comp.get('change_percentage', 0):+.1f}%)")
            lines.append("")
            
            # Distance
            distance_comp = metrics.get("distance_comparison", {})
            lines.append(f"📏 Distance totale:")
            lines.append(f"   V1: {distance_comp.get('v1_distance', 0):.0f}m")
            lines.append(f"   V2: {distance_comp.get('v2_distance', 0):.0f}m")
            lines.append(f"   Amélioration: {distance_comp.get('improvement_percentage', 0):+.1f}%")
            lines.append("")
            
            # Efficacité
            efficiency = metrics.get("efficiency_metrics", {})
            lines.append(f"⚡ Efficacité moyenne par tour:")
            lines.append(f"   V1: {efficiency.get('v1_avg_points_per_tour', 0):.1f} points/tour, {efficiency.get('v1_avg_distance_per_tour', 0):.0f}m/tour")
            lines.append(f"   V2: {efficiency.get('v2_avg_points_per_tour', 0):.1f} points/tour, {efficiency.get('v2_avg_distance_per_tour', 0):.0f}m/tour")
            lines.append("")
            
            # Isolation
            isolation = metrics.get("isolation_comparison", {})
            if isolation.get("isolation_increase", 0) > 0:
                lines.append(f"⚠️  Tours isolés (1 point):")
                lines.append(f"   V1: {isolation.get('v1_isolated_tours', 0)} tours")
                lines.append(f"   V2: {isolation.get('v2_isolated_tours', 0)} tours")
                lines.append(f"   Augmentation: +{isolation.get('isolation_increase', 0)}")
                lines.append("")
        
        # Comparaison détaillée des tours
        v1_analysis = comparison.get("v1_analysis")
        v2_analysis = comparison.get("v2_analysis")
        
        if v1_analysis and v2_analysis:
            lines.append("🎭 COMPARAISON DÉTAILLÉE DES TOURS")
            lines.append("=" * 50)
            
            visual = comparison.get("visual_comparison", {})
            side_by_side = visual.get("side_by_side_tours", [])
            
            for comp in side_by_side:
                index = comp["index"]
                v1_tour = comp["v1_tour"]
                v2_tour = comp["v2_tour"]
                
                lines.append(f"Tour #{index}:")
                
                if v1_tour:
                    lines.append(f"   V1: {v1_tour['points_count']} points, {v1_tour['distance']:.0f}m, {v1_tour['walking_time']:.0f}min")
                else:
                    lines.append(f"   V1: (pas de tour correspondant)")
                
                if v2_tour:
                    lines.append(f"   V2: {v2_tour['points_count']} points, {v2_tour['distance']:.0f}m, {v2_tour['walking_time']:.0f}min")
                    if v2_tour['points_count'] == 1:
                        lines.append(f"       ⚠️  Tour isolé: {v2_tour['points_names'][0] if v2_tour['points_names'] else 'Unknown'}")
                else:
                    lines.append(f"   V2: (pas de tour correspondant)")
                
                lines.append("")
        
        # Recommandations
        recommendations = comparison.get("recommendations", [])
        if recommendations:
            lines.append("💡 RECOMMANDATIONS")
            lines.append("=" * 30)
            
            for rec in recommendations:
                priority_emoji = {"high": "🔥", "medium": "⚠️", "positive": "✅", "low": "💭"}.get(rec.get("priority", "low"), "💭")
                lines.append(f"{priority_emoji} {rec.get('title', 'Recommandation')}")
                lines.append(f"   {rec.get('description', 'Aucune description')}")
                if 'suggestion' in rec:
                    lines.append(f"   💡 {rec['suggestion']}")
                lines.append("")
        
        lines.append("🎉 === FIN DE LA COMPARAISON ===")
        
        return "\\n".join(lines)
    
    def save_comparison_report(self, comparison: Dict[str, Any]) -> tuple[str, str]:
        """
        💾 Sauvegarde le rapport de comparaison
        """
        city = comparison.get("city", "unknown")
        country = comparison.get("country", "unknown")
        
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        base_filename = f"utils/comparison_v1_vs_v2_{city}_{country}_{timestamp}"
        json_file = f"{base_filename}.json"
        txt_file = f"{base_filename}.txt"
        
        # Sauvegarder JSON
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(comparison, f, ensure_ascii=False, indent=2)
        
        # Sauvegarder rapport lisible
        report_text = self.generate_comparison_report(comparison)
        with open(txt_file, "w", encoding="utf-8") as f:
            f.write(report_text)
        
        print(f"📋 Rapports de comparaison sauvegardés:")
        print(f"   • JSON: {json_file}")
        print(f"   • Lisible: {txt_file}")
        
        return json_file, txt_file