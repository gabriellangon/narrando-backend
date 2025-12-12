"""
Client ElevenLabs utilisant le SDK officiel v2.14.0
"""
import os
from typing import Dict, Optional
from dotenv import load_dotenv
from clients.base_tts_client import BaseTTSClient

try:
    from elevenlabs.client import ElevenLabs
    from elevenlabs import Voice, VoiceSettings
    ELEVENLABS_AVAILABLE = True
except ImportError:
    print("⚠️ ElevenLabs SDK non installé. Exécutez: pip install elevenlabs")
    ELEVENLABS_AVAILABLE = False

load_dotenv()


class ElevenLabsClient(BaseTTSClient):
    def __init__(self):
        """Initialise le client ElevenLabs avec le SDK officiel"""
        if not ELEVENLABS_AVAILABLE:
            raise ImportError("ElevenLabs SDK non disponible")
            
        self.api_key = os.getenv('ELEVENLABS_API_KEY')
        self.voice_id = os.getenv('ELEVENLABS_VOICE_ID', 'JBFqnCBsd6RMkjVDRZzb')  # George par défaut
        
        if not self.api_key:
            print("⚠️ ELEVENLABS_API_KEY non configurée")
            self.client = None
            return
        
        try:
            self.client = ElevenLabs(api_key=self.api_key)
            print(f"✅ ElevenLabs SDK v2.14.0 initialisé avec voice_id: {self.voice_id}")
        except Exception as e:
            print(f"❌ Erreur initialisation ElevenLabs: {e}")
            self.client = None
        
        self.voice_map = {}
        voice_map_env = os.getenv('ELEVENLABS_VOICE_MAP', '')
        for entry in voice_map_env.split(','):
            if '=' in entry:
                lang, voice = entry.split('=', 1)
                lang = lang.strip().lower()
                voice = voice.strip()
                if lang and voice:
                    self.voice_map[lang] = voice
        if self.voice_id:
            self.voice_map.setdefault('en', self.voice_id)

    def get_voice_id(self, language_code: str) -> str:
        if not language_code:
            return self.voice_id
        lang = language_code.lower()
        if lang in self.voice_map:
            return self.voice_map[lang]
        if '-' in lang:
            base = lang.split('-')[0]
            if base in self.voice_map:
                return self.voice_map[base]
        return self.voice_id

    def generate_audio(self, text: str, voice_settings: Optional[Dict] = None, voice_id: Optional[str] = None) -> bytes:
        """
        Génère un audio à partir d'un texte
        
        Args:
            text: Texte à convertir en audio
            voice_settings: Paramètres de voix personnalisés
            
        Returns:
            bytes: Contenu audio en format MP3
        """
        if not self.client:
            raise Exception("Client ElevenLabs non initialisé")
        
        # Paramètres de voix par défaut pour NARRATION TOURISTIQUE
        default_settings = {
            "stability": 0.3,           # Plus bas = plus d'expression et variabilité
            "similarity_boost": 0.9,    # Plus haut = garde le caractère de la voix  
            "style": 0.7,               # Plus haut = plus d'émotion et enthousiasme
            "use_speaker_boost": True   # Active l'amplification pour plus de clarté
        }
        
        if voice_settings:
            default_settings.update(voice_settings)
        
        try:
            # Utiliser le SDK officiel
            audio_generator = self.client.text_to_speech.convert(
                text=text,
                voice_id=voice_id or self.voice_id,
                model_id="eleven_multilingual_v2",
                output_format="mp3_44100_128",
                voice_settings=VoiceSettings(
                    stability=default_settings["stability"],
                    similarity_boost=default_settings["similarity_boost"],
                    style=default_settings["style"],
                    use_speaker_boost=default_settings["use_speaker_boost"]
                )
            )
            
            # Convertir le générateur en bytes
            audio_data = b''.join(audio_generator)
            
            print(f"✅ Audio généré avec SDK: {len(audio_data)} bytes")
            return audio_data
            
        except Exception as e:
            raise Exception(f"Erreur génération audio ElevenLabs SDK: {str(e)}")

    def generate_audio_stream(self, text: str, voice_settings: Optional[Dict] = None, voice_id: Optional[str] = None):
        """
        Génère un stream audio (pour le streaming en temps réel)
        
        Args:
            text: Texte à convertir
            voice_settings: Paramètres de voix
            
        Returns:
            Generator: Stream audio
        """
        if not self.client:
            raise Exception("Client ElevenLabs non initialisé")
        
        default_settings = {
            "stability": 0.5,
            "similarity_boost": 0.8,
            "style": 0.5,
            "use_speaker_boost": True
        }
        
        if voice_settings:
            default_settings.update(voice_settings)
        
        try:
            return self.client.text_to_speech.convert_stream(
                text=text,
                voice_id=voice_id or self.voice_id,
                model_id="eleven_multilingual_v2",
                output_format="mp3_44100_128",
                voice_settings=VoiceSettings(**default_settings)
            )
        except Exception as e:
            raise Exception(f"Erreur stream audio: {str(e)}")

    def get_available_voices(self) -> list:
        """
        Récupère la liste des voix disponibles
        
        Returns:
            list: Liste des voix disponibles
        """
        if not self.client:
            raise Exception("Client ElevenLabs non initialisé")
        
        try:
            voices = self.client.voices.get_all()
            
            voices_list = []
            for voice in voices.voices:
                voices_list.append({
                    'voice_id': voice.voice_id,
                    'name': voice.name,
                    'category': voice.category,
                    'description': getattr(voice, 'description', ''),
                    'preview_url': getattr(voice, 'preview_url', ''),
                    'available_for_tiers': getattr(voice, 'available_for_tiers', [])
                })
            
            print(f"✅ {len(voices_list)} voix disponibles")
            return voices_list
            
        except Exception as e:
            raise Exception(f"Erreur récupération voix: {str(e)}")

    def get_voice_info(self, voice_id: Optional[str] = None) -> dict:
        """
        Récupère les informations d'une voix spécifique
        
        Args:
            voice_id: ID de la voix (utilise self.voice_id par défaut)
            
        Returns:
            dict: Informations de la voix
        """
        if not self.client:
            raise Exception("Client ElevenLabs non initialisé")
        
        target_voice_id = voice_id or self.voice_id
        
        try:
            voice = self.client.voices.get(voice_id=target_voice_id)
            
            return {
                'voice_id': voice.voice_id,
                'name': voice.name,
                'category': voice.category,
                'description': getattr(voice, 'description', ''),
                'preview_url': getattr(voice, 'preview_url', ''),
                'settings': getattr(voice, 'settings', {}),
                'available_for_tiers': getattr(voice, 'available_for_tiers', [])
            }
            
        except Exception as e:
            raise Exception(f"Erreur info voix {target_voice_id}: {str(e)}")

    def get_user_info(self) -> dict:
        """
        Récupère les informations utilisateur (quotas, usage)

        Returns:
            dict: Informations utilisateur
        """
        if not self.client:
            raise Exception("Client ElevenLabs non initialisé")

        try:
            # L'API ElevenLabs v2.14.0 utilise user.subscription au lieu de users.get_subscription()
            user_info = self.client.user.subscription()

            return {
                'tier': getattr(user_info, 'tier', 'unknown'),
                'character_count': getattr(user_info, 'character_count', 0),
                'character_limit': getattr(user_info, 'character_limit', 0),
                'can_extend_character_limit': getattr(user_info, 'can_extend_character_limit', False),
                'allowed_to_extend_character_limit': getattr(user_info, 'allowed_to_extend_character_limit', False),
                'next_character_count_reset_unix': getattr(user_info, 'next_character_count_reset_unix', 0),
                'voice_limit': getattr(user_info, 'voice_limit', 0),
                'max_voice_add_edits': getattr(user_info, 'max_voice_add_edits', 0),
                'voice_add_edit_counter': getattr(user_info, 'voice_add_edit_counter', 0),
                'professional_voice_limit': getattr(user_info, 'professional_voice_limit', 0),
                'can_extend_voice_limit': getattr(user_info, 'can_extend_voice_limit', False),
                'can_use_instant_voice_cloning': getattr(user_info, 'can_use_instant_voice_cloning', False),
                'can_use_professional_voice_cloning': getattr(user_info, 'can_use_professional_voice_cloning', False),
                'currency': getattr(user_info, 'currency', 'USD'),
                'status': getattr(user_info, 'status', 'active')
            }

        except Exception as e:
            raise Exception(f"Erreur info utilisateur: {str(e)}")

    def test_connection(self) -> bool:
        """
        Test la connexion à l'API ElevenLabs
        
        Returns:
            bool: True si la connexion fonctionne
        """
        if not self.client:
            print("❌ Client ElevenLabs non initialisé")
            return False
            
        try:
            voices = self.get_available_voices()
            user_info = self.get_user_info()
            
            print(f"✅ ElevenLabs SDK connecté")
            print(f"   Tier: {user_info.get('tier', 'N/A')}")
            print(f"   Caractères utilisés: {user_info.get('character_count', 0)}/{user_info.get('character_limit', 'unlimited')}")
            print(f"   Voix disponibles: {len(voices)}")
            return True
            
        except Exception as e:
            print(f"❌ Test connexion ElevenLabs failed: {e}")
            return False

    def get_narrative_voice_settings(self, style: str = "enthusiastic") -> dict:
        """
        Retourne des paramètres de voix optimisés pour différents styles narratifs
        
        Args:
            style: Style de narration ('enthusiastic', 'calm', 'dramatic', 'informative')
            
        Returns:
            dict: Paramètres de voix optimisés
        """
        styles = {
            "enthusiastic": {
                "stability": 0.2,           # Très expressif
                "similarity_boost": 0.9,    # Garde l'identité de la voix
                "style": 0.8,               # Très émotionnel et enthousiaste
                "use_speaker_boost": True,
                "description": "Parfait pour présenter des attractions avec passion"
            },
            "calm": {
                "stability": 0.6,           # Plus stable et posé
                "similarity_boost": 0.8,    
                "style": 0.4,               # Moins d'émotion, plus informatif
                "use_speaker_boost": True,
                "description": "Idéal pour les instructions et informations pratiques"
            },
            "dramatic": {
                "stability": 0.1,           # Très variable pour créer du suspense
                "similarity_boost": 0.9,    
                "style": 0.9,               # Maximum d'émotion
                "use_speaker_boost": True,
                "description": "Parfait pour les anecdotes historiques dramatiques"
            },
            "informative": {
                "stability": 0.7,           # Très stable et clair
                "similarity_boost": 0.7,    
                "style": 0.3,               # Neutre et informatif
                "use_speaker_boost": True,
                "description": "Optimal pour les faits, horaires, prix"
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
            language_label: Nom lisible de la langue (pour logs/QA)
            
        Returns:
            bytes: Audio optimisé pour le guide touristique
        """
        # Mapper les types de contenu aux styles narratifs
        content_to_style = {
            "attraction": "enthusiastic",    # Présentation d'attractions
            "history": "dramatic",          # Anecdotes historiques  
            "practical": "informative",     # Infos pratiques (horaires, prix)
            "anecdote": "dramatic",         # Anecdotes captivantes
            "welcome": "enthusiastic",      # Messages d'accueil
            "transition": "calm"            # Transitions entre points
        }
        
        style = content_to_style.get(content_type, "enthusiastic")
        voice_settings = self.get_narrative_voice_settings(style)
        
        lang_display = language_label or "Langue inconnue"
        print(f"🎭 Style narratif: {style} - {voice_settings['description']} ({lang_display})")
        
        return self.generate_audio(text, voice_settings, voice_id=voice_id)

    def estimate_cost(self, text: str) -> dict:
        """
        Estime le coût de génération d'un audio
        
        Args:
            text: Texte à analyser
            
        Returns:
            dict: Estimation du coût
        """
        char_count = len(text)
        
        # Coûts approximatifs par tier (2024)
        cost_per_1000_chars = {
            'free': 0.0,           # 10,000 chars/month gratuits
            'starter': 0.0003,     # $5/month pour ~16,667 chars
            'creator': 0.0002,     # $22/month pour ~100,000 chars  
            'pro': 0.00015,        # $99/month pour ~500,000 chars
            'scale': 0.0001,       # $330/month pour ~2,000,000 chars
        }
        
        # Estimation basée sur le tier Starter (défaut)
        estimated_cost = (char_count / 1000) * cost_per_1000_chars.get('starter', 0.0003)
        
        return {
            'character_count': char_count,
            'estimated_cost_usd': round(estimated_cost, 4),
            'voice_id': self.voice_id,
            'model': 'eleven_multilingual_v2',
            'note': 'Coût approximatif - vérifiez votre tier réel'
        }


def main():
    """Test rapide du client ElevenLabs"""
    print("🧪 Test ElevenLabs SDK Client")
    
    try:
        client = ElevenLabsClient()
        
        if client.test_connection():
            print("\n🎵 Test estimation coût...")
            
            test_text = "Bonjour ! Ceci est un test du SDK ElevenLabs en français."
            cost_estimate = client.estimate_cost(test_text)
            
            print(f"💰 Coût estimé: ${cost_estimate['estimated_cost_usd']} pour {cost_estimate['character_count']} caractères")
            print(f"🎙️ Voix: {cost_estimate['voice_id']}")
            print(f"📝 Note: {cost_estimate['note']}")
            
            # Générer un petit audio test (décommentez pour tester réellement)
            # audio_data = client.generate_audio(test_text)
            # print(f"✅ Audio généré: {len(audio_data)} bytes")
            
        else:
            print("❌ Connexion ElevenLabs échouée")
            
    except Exception as e:
        print(f"💥 Erreur: {e}")


if __name__ == "__main__":
    main()
