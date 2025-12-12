"""
Client OpenAI Text-to-Speech
Compatible avec l'interface ElevenLabsClient pour remplacement transparent
"""
import os
import sys
from typing import Dict, Optional
from dotenv import load_dotenv

# Ajouter le répertoire parent au path pour imports
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clients.base_tts_client import BaseTTSClient

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    print("⚠️ OpenAI SDK non installé. Exécutez: pip install openai")
    OPENAI_AVAILABLE = False

load_dotenv()


class OpenAITTSClient(BaseTTSClient):
    """
    Client OpenAI Text-to-Speech avec interface compatible ElevenLabs

    Voix disponibles:
    - alloy: Voix neutre et équilibrée
    - echo: Voix masculine claire
    - fable: Voix britannique expressive
    - onyx: Voix masculine profonde
    - nova: Voix féminine enthousiaste (recommandée pour guides touristiques)
    - shimmer: Voix féminine chaleureuse
    """

    def __init__(self):
        """Initialise le client OpenAI TTS"""
        if not OPENAI_AVAILABLE:
            raise ImportError("OpenAI SDK non disponible")

        self.api_key = os.getenv('OPENAI_API_KEY')

        if not self.api_key:
            print("⚠️ OPENAI_API_KEY non configurée")
            self.client = None
            return

        try:
            self.client = OpenAI(api_key=self.api_key)
            # Voix par défaut optimale pour narration touristique
            self.voice_id = os.getenv('OPENAI_VOICE', 'nova')
            print(f"✅ OpenAI TTS initialisé avec voix: {self.voice_id}")
        except Exception as e:
            print(f"❌ Erreur initialisation OpenAI TTS: {e}")
            self.client = None

        # Mapping des langues vers les voix optimales
        self.voice_map = {}
        voice_map_env = os.getenv('OPENAI_VOICE_MAP', '')
        for entry in voice_map_env.split(','):
            if '=' in entry:
                lang, voice = entry.split('=', 1)
                lang = lang.strip().lower()
                voice = voice.strip()
                if lang and voice:
                    self.voice_map[lang] = voice

        # Configuration par défaut si aucune configuration spécifique
        if not self.voice_map:
            self.voice_map = {
                'en': 'nova',  # Féminine enthousiaste pour anglais
                'fr': 'nova',  # Multilingue compatible français
                'es': 'nova',  # Multilingue compatible espagnol
                'it': 'nova',  # Multilingue compatible italien
                'de': 'nova',  # Multilingue compatible allemand
                'pt': 'nova',  # Multilingue compatible portugais
            }

    def get_voice_id(self, language_code: str) -> str:
        """
        Retourne la voix optimale pour une langue donnée

        Args:
            language_code: Code langue (en, fr, es, etc.)

        Returns:
            str: Nom de la voix OpenAI
        """
        if not language_code:
            return self.voice_id

        lang = language_code.lower()
        if lang in self.voice_map:
            return self.voice_map[lang]

        # Gestion des codes langue avec région (ex: en-US -> en)
        if '-' in lang:
            base = lang.split('-')[0]
            if base in self.voice_map:
                return self.voice_map[base]

        return self.voice_id

    def generate_audio(
        self,
        text: str,
        voice_settings: Optional[Dict] = None,
        voice_id: Optional[str] = None
    ) -> bytes:
        """
        Génère un audio à partir d'un texte

        Args:
            text: Texte à convertir en audio
            voice_settings: Paramètres de voix (ignorés pour OpenAI - compatibilité API)
            voice_id: ID de la voix à utiliser (alloy, echo, fable, onyx, nova, shimmer)

        Returns:
            bytes: Contenu audio en format MP3
        """
        if not self.client:
            raise Exception("Client OpenAI TTS non initialisé")

        # Note: OpenAI TTS ne supporte pas les paramètres de voix détaillés comme ElevenLabs
        # Les voice_settings sont ignorés pour la compatibilité API

        try:
            target_voice = voice_id or self.voice_id

            # Valider la voix
            valid_voices = ['alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer']
            if target_voice not in valid_voices:
                print(f"⚠️ Voix {target_voice} invalide, utilisation de nova par défaut")
                target_voice = 'nova'

            # Générer l'audio avec OpenAI TTS
            # Modèle tts-1-hd pour qualité optimale (tts-1 pour vitesse)
            response = self.client.audio.speech.create(
                model="tts-1-hd",  # Haute qualité
                voice=target_voice,
                input=text,
                response_format="mp3",
                speed=1.0  # Vitesse normale
            )

            # Convertir la réponse en bytes
            audio_data = response.content

            print(f"✅ Audio généré avec OpenAI TTS: {len(audio_data)} bytes (voix: {target_voice})")
            return audio_data

        except Exception as e:
            raise Exception(f"Erreur génération audio OpenAI TTS: {str(e)}")

    def generate_audio_stream(
        self,
        text: str,
        voice_settings: Optional[Dict] = None,
        voice_id: Optional[str] = None
    ):
        """
        Génère un stream audio (pour le streaming en temps réel)

        Note: OpenAI TTS ne supporte pas nativement le streaming dans la même API
        Cette méthode génère l'audio complet puis le retourne comme générateur
        pour maintenir la compatibilité API

        Args:
            text: Texte à convertir
            voice_settings: Paramètres de voix (ignorés)
            voice_id: ID de la voix

        Returns:
            Generator: Stream audio
        """
        if not self.client:
            raise Exception("Client OpenAI TTS non initialisé")

        try:
            # Générer l'audio complet
            audio_data = self.generate_audio(text, voice_settings, voice_id)

            # Simuler un stream en retournant par chunks
            chunk_size = 4096
            for i in range(0, len(audio_data), chunk_size):
                yield audio_data[i:i + chunk_size]

        except Exception as e:
            raise Exception(f"Erreur stream audio OpenAI: {str(e)}")

    def get_available_voices(self) -> list:
        """
        Récupère la liste des voix disponibles

        Returns:
            list: Liste des voix disponibles OpenAI
        """
        # OpenAI TTS a un ensemble fixe de voix
        return [
            {
                'voice_id': 'alloy',
                'name': 'Alloy',
                'category': 'standard',
                'description': 'Voix neutre et équilibrée',
                'preview_url': '',
                'available_for_tiers': ['free', 'paid']
            },
            {
                'voice_id': 'echo',
                'name': 'Echo',
                'category': 'standard',
                'description': 'Voix masculine claire',
                'preview_url': '',
                'available_for_tiers': ['free', 'paid']
            },
            {
                'voice_id': 'fable',
                'name': 'Fable',
                'category': 'standard',
                'description': 'Voix britannique expressive',
                'preview_url': '',
                'available_for_tiers': ['free', 'paid']
            },
            {
                'voice_id': 'onyx',
                'name': 'Onyx',
                'category': 'standard',
                'description': 'Voix masculine profonde',
                'preview_url': '',
                'available_for_tiers': ['free', 'paid']
            },
            {
                'voice_id': 'nova',
                'name': 'Nova',
                'category': 'standard',
                'description': 'Voix féminine enthousiaste (recommandée pour guides touristiques)',
                'preview_url': '',
                'available_for_tiers': ['free', 'paid']
            },
            {
                'voice_id': 'shimmer',
                'name': 'Shimmer',
                'category': 'standard',
                'description': 'Voix féminine chaleureuse',
                'preview_url': '',
                'available_for_tiers': ['free', 'paid']
            }
        ]

    def get_voice_info(self, voice_id: Optional[str] = None) -> dict:
        """
        Récupère les informations d'une voix spécifique

        Args:
            voice_id: ID de la voix

        Returns:
            dict: Informations de la voix
        """
        target_voice_id = voice_id or self.voice_id

        voices = self.get_available_voices()
        for voice in voices:
            if voice['voice_id'] == target_voice_id:
                return voice

        raise Exception(f"Voix {target_voice_id} non trouvée")

    def get_user_info(self) -> dict:
        """
        Récupère les informations utilisateur (quotas, usage)

        Note: OpenAI ne fournit pas d'API publique pour les quotas TTS
        Cette méthode retourne des informations génériques pour compatibilité

        Returns:
            dict: Informations utilisateur
        """
        return {
            'tier': 'OpenAI',
            'character_count': 0,
            'character_limit': 'API-based',
            'note': 'OpenAI TTS facture par requête, pas de quota de caractères publique',
            'model': 'tts-1-hd',
            'voices_available': 6
        }

    def test_connection(self) -> bool:
        """
        Test la connexion à l'API OpenAI TTS

        Returns:
            bool: True si la connexion fonctionne
        """
        if not self.client:
            print("❌ Client OpenAI TTS non initialisé")
            return False

        try:
            # Test avec un texte court
            test_text = "Test de connexion OpenAI TTS."
            audio_data = self.generate_audio(test_text)

            print(f"✅ OpenAI TTS connecté et fonctionnel")
            print(f"   Voix par défaut: {self.voice_id}")
            print(f"   Voix disponibles: 6 (alloy, echo, fable, onyx, nova, shimmer)")
            print(f"   Audio test généré: {len(audio_data)} bytes")
            return True

        except Exception as e:
            print(f"❌ Test connexion OpenAI TTS échoué: {e}")
            return False

    def get_narrative_voice_settings(self, style: str = "enthusiastic") -> dict:
        """
        Retourne des paramètres de voix optimisés pour différents styles narratifs

        Note: OpenAI TTS ne supporte pas les paramètres détaillés de voix
        Cette méthode est maintenue pour compatibilité API mais retourne
        des suggestions de voix plutôt que des paramètres

        Args:
            style: Style de narration ('enthusiastic', 'calm', 'dramatic', 'informative')

        Returns:
            dict: Recommandations de voix pour le style
        """
        styles = {
            "enthusiastic": {
                "voice": "nova",
                "description": "Voix féminine enthousiaste, parfaite pour présenter des attractions"
            },
            "calm": {
                "voice": "shimmer",
                "description": "Voix féminine chaleureuse, idéale pour informations pratiques"
            },
            "dramatic": {
                "voice": "fable",
                "description": "Voix britannique expressive, parfaite pour anecdotes historiques"
            },
            "informative": {
                "voice": "alloy",
                "description": "Voix neutre et claire, optimale pour faits et horaires"
            }
        }

        return styles.get(style, styles["enthusiastic"])

    def generate_tourist_guide_audio(
        self,
        text: str,
        content_type: str = "attraction",
        voice_id: Optional[str] = None,
        language_label: Optional[str] = None
    ) -> bytes:
        """
        Génère un audio optimisé pour guide touristique selon le type de contenu

        Args:
            text: Texte à convertir
            content_type: Type de contenu ('attraction', 'history', 'practical', 'anecdote')
            voice_id: ID de la voix à utiliser (optionnel)
            language_label: Nom lisible de la langue (pour logs/QA)

        Returns:
            bytes: Audio optimisé pour le guide touristique
        """
        # Mapper les types de contenu aux voix optimales
        content_to_voice = {
            "attraction": "nova",      # Présentation enthousiaste
            "history": "fable",        # Narration dramatique
            "practical": "alloy",      # Information claire
            "anecdote": "fable",       # Récit expressif
            "welcome": "nova",         # Accueil chaleureux
            "transition": "shimmer"    # Transition douce
        }

        # Sélectionner la voix appropriée
        if not voice_id:
            voice_id = content_to_voice.get(content_type, "nova")

        lang_display = language_label or "Langue inconnue"
        print(f"🎭 Type de contenu: {content_type} - Voix: {voice_id} ({lang_display})")

        return self.generate_audio(text, voice_id=voice_id)

    def estimate_cost(self, text: str) -> dict:
        """
        Estime le coût de génération d'un audio

        Args:
            text: Texte à analyser

        Returns:
            dict: Estimation du coût
        """
        char_count = len(text)

        # Prix OpenAI TTS (Janvier 2025)
        # tts-1: $0.015 / 1K caractères
        # tts-1-hd: $0.030 / 1K caractères
        cost_per_1000_chars_hd = 0.030

        estimated_cost = (char_count / 1000) * cost_per_1000_chars_hd

        return {
            'character_count': char_count,
            'estimated_cost_usd': round(estimated_cost, 4),
            'voice_id': self.voice_id,
            'model': 'tts-1-hd',
            'note': 'Prix basé sur tts-1-hd à $0.030/1K caractères'
        }


def main():
    """Test rapide du client OpenAI TTS"""
    print("🧪 Test OpenAI TTS Client")

    try:
        client = OpenAITTSClient()

        if client.test_connection():
            print("\n🎵 Test estimation coût...")

            test_text = "Bonjour ! Ceci est un test du SDK OpenAI TTS en français."
            cost_estimate = client.estimate_cost(test_text)

            print(f"💰 Coût estimé: ${cost_estimate['estimated_cost_usd']} pour {cost_estimate['character_count']} caractères")
            print(f"🎙️ Voix: {cost_estimate['voice_id']}")
            print(f"📝 Note: {cost_estimate['note']}")

            print("\n🎤 Voix disponibles:")
            voices = client.get_available_voices()
            for voice in voices:
                print(f"   - {voice['voice_id']}: {voice['description']}")

        else:
            print("❌ Connexion OpenAI TTS échouée")

    except Exception as e:
        print(f"💥 Erreur: {e}")


if __name__ == "__main__":
    main()
