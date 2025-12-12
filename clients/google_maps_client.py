"""
Client pour l'API Google Maps Search
"""
import os
import json
import urllib.parse
from typing import Dict, List, Optional, Any
import requests
from dotenv import load_dotenv
from utils.logging_config import get_logger

# Charger les variables d'environnement
load_dotenv()

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


DEFAULT_TIMEOUT = _get_timeout_seconds("GOOGLE_MAPS_TIMEOUT_SECONDS", 10.0)

class GoogleMapsClient:
    """
    Client pour interagir avec l'API Google Maps Places
    """
    def __init__(self):
        """
        Initialise le client Google Maps avec la clé API
        """
        self.api_key = os.getenv("GOOGLE_PLACES_API_KEY")
        if not self.api_key:
            raise ValueError("La clé API Google Places n'est pas définie dans le fichier .env")
        
        self.base_url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
        self.place_details_url = "https://maps.googleapis.com/maps/api/place/details/json"
    
    def search_tourist_attractions(self, city: str, country: str, max_results: int = 30) -> List[Dict[str, Any]]:
        """
        Recherche les attractions touristiques dans une ville et un pays spécifiques
        
        Args:
            city: Nom de la ville
            country: Nom du pays
            max_results: Nombre maximum de résultats à retourner (défaut: 30)
            
        Returns:
            Liste des attractions touristiques trouvées
        """
        # Formater la requête pour la recherche
        query = f"{city} {country} touristic attractions"
        encoded_query = urllib.parse.quote(query)
        
        # Préparer l'URL de la requête
        url = f"{self.base_url}?query={encoded_query}&language=en&key={self.api_key}"
        
        # Initialiser la liste des résultats
        all_results = []
        
        # Effectuer la première requête
        response = requests.get(url, timeout=DEFAULT_TIMEOUT)
        if response.status_code != 200:
            raise Exception(f"Erreur lors de la requête à l'API Google Maps: {response.status_code}")
        
        data = response.json()
        
        # Ajouter les résultats à la liste
        all_results.extend(data.get("results", []))
        
        # Gérer la pagination si nécessaire
        next_page_token = data.get("next_page_token")
        
        while next_page_token and len(all_results) < max_results:
            # Attendre un peu avant de faire la requête suivante (requis par l'API Google)
            import time
            time.sleep(2)
            
            # Préparer l'URL pour la page suivante
            next_page_url = f"{self.base_url}?pagetoken={next_page_token}&language=en&key={self.api_key}"
            
            # Effectuer la requête pour la page suivante
            response = requests.get(next_page_url, timeout=DEFAULT_TIMEOUT)
            if response.status_code != 200:
                break
            
            data = response.json()
            
            # Ajouter les résultats à la liste
            all_results.extend(data.get("results", []))
            
            # Mettre à jour le token pour la page suivante
            next_page_token = data.get("next_page_token")
        
        # Limiter le nombre de résultats si nécessaire
        return all_results[:max_results]
    
    def get_city_info(self, city: str, country: str) -> Dict[str, Any]:
        """
        Récupère les informations d'une ville, incluant son place_id et les informations de pays
        
        Args:
            city: Nom de la ville
            country: Nom du pays
            
        Returns:
            Dictionnaire contenant les informations de la ville incluant place_id et country_iso_code
        """
        # Formater la requête pour la recherche de la ville
        query = f"{city} {country}"
        encoded_query = urllib.parse.quote(query)
        
        # Préparer l'URL de la requête
        url = f"{self.base_url}?query={encoded_query}&type=locality&language=en&key={self.api_key}"
        
        try:
            # Effectuer la requête pour trouver la ville
            response = requests.get(url, timeout=DEFAULT_TIMEOUT)
            if response.status_code != 200:
                raise Exception(f"Erreur lors de la requête à l'API Google Maps: {response.status_code}")
            
            data = response.json()
            results = data.get("results", [])
            
            if not results:
                print(f"Aucune ville trouvée pour '{city}, {country}'")
                return {
                    "city": city,
                    "country": country,
                    "place_id": None,
                    "country_iso_code": None,
                    "formatted_address": None
                }
            
            # Prendre le premier résultat (le plus pertinent)
            city_result = results[0]
            place_id = city_result.get("place_id")
            formatted_address = city_result.get("formatted_address")
            
            # Récupérer les détails du lieu pour obtenir le code ISO du pays
            place_details_url = (
                f"{self.place_details_url}?place_id={place_id}"
                f"&fields=address_components&language=en&key={self.api_key}"
            )
            details_response = requests.get(place_details_url, timeout=DEFAULT_TIMEOUT)
            
            country_iso_code = None
            if details_response.status_code == 200:
                details_data = details_response.json()
                result = details_data.get("result", {})
                address_components = result.get("address_components", [])
                
                # Rechercher le composant de type 'country' pour récupérer le code ISO
                for component in address_components:
                    if "country" in component.get("types", []):
                        country_iso_code = component.get("short_name")
                        break
            
            return {
                "city": city,
                "country": country,
                "place_id": place_id,
                "country_iso_code": country_iso_code,
                "formatted_address": formatted_address
            }
            
        except Exception as e:
            print(f"Erreur lors de la récupération des informations de la ville: {str(e)}")
            return {
                "city": city,
                "country": country,
                "place_id": None,
                "country_iso_code": None,
                "formatted_address": None
            }

    def save_results_to_json(self, results: List[Dict[str, Any]], city: str, country: str) -> str:
        """
        Sauvegarde les résultats dans un fichier JSON
        
        Args:
            results: Liste des résultats à sauvegarder
            city: Nom de la ville
            country: Nom du pays
            
        Returns:
            Chemin du fichier JSON créé
        """
        # Créer le nom du fichier
        filename = f"data/{city.lower()}_{country.lower()}_attractions.json"
        
        # Importer le module time pour le timestamp
        import time
        
        # Créer le dictionnaire à sauvegarder
        data_to_save = {
            "city": city,
            "country": country,
            "timestamp": time.time(),
            "count": len(results),
            "attractions": results
        }
        
        # Sauvegarder les données dans un fichier JSON
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=2)
        
        return filename
