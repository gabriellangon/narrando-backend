"""
Module clients - Gestion des clients TTS et autres services
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Enregistrement des clients TTS dans la factory
from clients.base_tts_client import TTSClientFactory

# Import conditionnel pour éviter les erreurs si SDK non installé
try:
    from clients.openai_tts_client import OpenAITTSClient
    TTSClientFactory.register('openai', OpenAITTSClient)
except ImportError:
    print("⚠️ OpenAI TTS non disponible")

try:
    from clients.elevenlabs_client import ElevenLabsClient
    TTSClientFactory.register('elevenlabs', ElevenLabsClient)
except ImportError:
    print("⚠️ ElevenLabs non disponible")


def get_tts_client():
    """
    Retourne le client TTS configuré via variable d'environnement

    Variables d'environnement:
        TTS_PROVIDER: Service à utiliser ('openai' ou 'elevenlabs')
                      Par défaut: 'openai'

    Returns:
        BaseTTSClient: Instance du client TTS configuré

    Raises:
        ValueError: Si le provider n'est pas disponible
    """
    provider = os.getenv('TTS_PROVIDER', 'openai').lower()

    try:
        client = TTSClientFactory.create(provider)
        print(f"✅ Client TTS initialisé: {provider}")
        return client
    except ValueError as e:
        available = TTSClientFactory.list_available()
        print(f"❌ Erreur: {e}")
        print(f"   Providers disponibles: {', '.join(available)}")
        raise


__all__ = [
    'get_tts_client',
    'TTSClientFactory',
    'OpenAITTSClient',
    'ElevenLabsClient'
]
