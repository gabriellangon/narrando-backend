"""
Générateur d'URLs Google Photos à partir des photo_reference
🖼️ Convertit les tokens photo_reference en URLs complètes pour le frontend
"""
import os
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

class GooglePhotoURLGenerator:
    def __init__(self):
        """Initialise le générateur d'URLs Google Photos"""
        self.google_api_key = os.getenv("GOOGLE_PLACES_API_KEY")
        if not self.google_api_key:
            raise ValueError("🚨 Clé API Google manquante dans .env")
        
        self.photos_base_url = "https://maps.googleapis.com/maps/api/place/photo"
        print("🖼️ GooglePhotoURLGenerator initialisé")
    
    def generate_photo_url(self, photo_reference: str, max_width: int = 400, max_height: int = 400) -> str:
        """
        Génère une URL complète Google Photos depuis un photo_reference
        
        Args:
            photo_reference: Token de référence photo Google
            max_width: Largeur maximale de l'image (défaut: 400px)
            max_height: Hauteur maximale de l'image (défaut: 400px)
        
        Returns:
            URL complète de l'image Google Photos
        """
        if not photo_reference:
            return None
        
        # Construction de l'URL Google Photos API
        url = f"{self.photos_base_url}?photoreference={photo_reference}&maxwidth={max_width}&maxheight={max_height}&key={self.google_api_key}"
        
        return url
    
    def process_attraction_photos(self, photos: List[Dict[str, Any]], max_width: int = 400) -> List[Dict[str, Any]]:
        """
        Traite une liste de photos d'attraction pour générer les URLs complètes
        
        Args:
            photos: Liste des photos avec photo_reference
            max_width: Largeur maximale des images
        
        Returns:
            Liste des photos enrichies avec photo_url
        """
        if not photos:
            return []
        
        processed_photos = []
        
        for photo in photos:
            photo_reference = photo.get("photo_reference")
            if photo_reference:
                # Créer une copie enrichie de la photo
                processed_photo = photo.copy()
                processed_photo["photo_url"] = self.generate_photo_url(
                    photo_reference, 
                    max_width=max_width, 
                    max_height=max_width  # Garder ratio carré pour uniformité
                )
                processed_photos.append(processed_photo)
        
        return processed_photos
    
    def get_primary_photo_url(self, photos: List[Dict[str, Any]], max_width: int = 400) -> Optional[str]:
        """
        Récupère l'URL de la photo principale (première photo) d'une attraction
        
        Args:
            photos: Liste des photos de l'attraction
            max_width: Largeur maximale de l'image
        
        Returns:
            URL de la photo principale ou None
        """
        if not photos or len(photos) == 0:
            return None
        
        primary_photo = photos[0]  # Première photo = photo principale
        photo_reference = primary_photo.get("photo_reference")
        
        if photo_reference:
            return self.generate_photo_url(photo_reference, max_width=max_width)
        
        return None
    
    def bulk_process_attractions(self, attractions_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Traite en lot les données d'attractions pour enrichir avec photo URLs
        
        Args:
            attractions_data: Liste des données d'attractions
        
        Returns:
            Liste des attractions enrichies avec photo_urls
        """
        processed_attractions = []
        
        for attraction in attractions_data:
            processed_attraction = attraction.copy()
            photos = attraction.get("photos", [])
            
            if photos:
                # Enrichir toutes les photos avec URLs
                processed_attraction["photos"] = self.process_attraction_photos(photos)
                
                # Ajouter URL de la photo principale pour faciliter l'accès frontend
                processed_attraction["primary_photo_url"] = self.get_primary_photo_url(photos)
            else:
                processed_attraction["primary_photo_url"] = None
            
            processed_attractions.append(processed_attraction)
        
        return processed_attractions

# Fonction utilitaire standalone
def convert_photo_reference_to_url(photo_reference: str, max_width: int = 400) -> str:
    """
    Fonction utilitaire pour convertir rapidement un photo_reference en URL
    """
    generator = GooglePhotoURLGenerator()
    return generator.generate_photo_url(photo_reference, max_width=max_width)

if __name__ == "__main__":
    # Test du générateur
    print("🧪 Test GooglePhotoURLGenerator")
    
    # Exemple de photo_reference depuis les données
    test_photo_reference = "ATKogpd9biB0lm5gMG93ff47L_VTuQYvmz0SBkIrtZDKtcbf0IwEFr5qm_-62Qtn4oton-7Sx2_7-W2d5zt0GKCAiMtvmlJo1_500IQioptX3BulU4roN5Qti8jHju6_1FBVm2y73bgd86k_t1vMNyFq8zlNKkRNr-k6RzJp-QlwsBCIYPZjGpH1rh70O34BFltU23z8WJ_SbhGulBzZbtSF1VVV-44Wi5bpkvZjbGATb4Af4t-37CHLNW4WnS7a_GQpJxUe2rXYMc4-9jOLuhoRJbVTvQnDxYzQYwYXD29gbYsBYAMUbOHw-zWH3OAX_9-8vFr_4O6S8toc_U98H9fteDYEScEYBPQ22cJJAw1FWkeHAyJxKAEQZRE59d9AbnhtmPnt_-aSgXUT_2FNdkTqy77DsB5QksRECC9IEsT66pRiF_wkQ4YVvNdwhWqySLYBT1CYyVPbN0sY7-DRcs8-h2-IHgOsCLX-fAWd-_WRn-2Q1BC-4WBZ7qTKlhDi484oJrXtrftuAJ1h_WghOpE7dnMeSis-lw9bBG_PxB-9sTXIMQP-I7aUdAJH74ATyIUp5_3ALnIA"
    
    try:
        generator = GooglePhotoURLGenerator()
        url = generator.generate_photo_url(test_photo_reference, max_width=300)
        print(f"✅ URL générée: {url}")
        
        # Test avec données d'attraction
        test_photos = [
            {
                "height": 9000,
                "photo_reference": test_photo_reference,
                "width": 12000,
                "html_attributions": ["<a href=\"https://maps.google.com/maps/contrib/112579692810381688162\">Test User</a>"]
            }
        ]
        
        processed = generator.process_attraction_photos(test_photos)
        print(f"✅ Photos traitées: {len(processed)} photos avec URLs")
        
    except Exception as e:
        print(f"❌ Erreur test: {e}")