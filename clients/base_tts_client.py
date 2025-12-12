"""
Classe abstraite pour les clients Text-to-Speech
Permet une architecture modulaire et l'interchangeabilité des services TTS
"""
from abc import ABC, abstractmethod
from typing import Dict, Optional, Generator


class BaseTTSClient(ABC):
    """
    Interface abstraite pour tous les clients Text-to-Speech

    Cette classe définit l'interface commune que doivent implémenter
    tous les clients TTS (ElevenLabs, OpenAI, Google, etc.)
    """

    @abstractmethod
    def __init__(self):
        """
        Initialise le client TTS
        Doit configurer:
        - self.client: Instance du client API
        - self.voice_id: Voix par défaut
        - self.voice_map: Mapping langue -> voix
        """
        pass

    @abstractmethod
    def get_voice_id(self, language_code: str) -> str:
        """
        Retourne l'ID de voix approprié pour une langue

        Args:
            language_code: Code langue ISO (en, fr, es, etc.)

        Returns:
            str: ID de la voix à utiliser
        """
        pass

    @abstractmethod
    def generate_audio(
        self,
        text: str,
        voice_settings: Optional[Dict] = None,
        voice_id: Optional[str] = None
    ) -> bytes:
        """
        Génère un fichier audio à partir d'un texte

        Args:
            text: Texte à convertir en audio
            voice_settings: Paramètres de voix spécifiques au service
            voice_id: ID de la voix à utiliser (optionnel)

        Returns:
            bytes: Contenu audio en format MP3

        Raises:
            Exception: Si la génération échoue
        """
        pass

    @abstractmethod
    def generate_audio_stream(
        self,
        text: str,
        voice_settings: Optional[Dict] = None,
        voice_id: Optional[str] = None
    ) -> Generator[bytes, None, None]:
        """
        Génère un stream audio pour le streaming en temps réel

        Args:
            text: Texte à convertir
            voice_settings: Paramètres de voix
            voice_id: ID de la voix

        Returns:
            Generator: Stream de chunks audio

        Raises:
            Exception: Si la génération échoue
        """
        pass

    @abstractmethod
    def get_available_voices(self) -> list:
        """
        Récupère la liste des voix disponibles

        Returns:
            list: Liste de dictionnaires contenant:
                - voice_id: Identifiant de la voix
                - name: Nom lisible de la voix
                - category: Catégorie (standard, premium, etc.)
                - description: Description de la voix
                - preview_url: URL de prévisualisation (optionnel)
                - available_for_tiers: Tiers d'accès (optionnel)
        """
        pass

    @abstractmethod
    def get_voice_info(self, voice_id: Optional[str] = None) -> dict:
        """
        Récupère les informations détaillées d'une voix

        Args:
            voice_id: ID de la voix (utilise la voix par défaut si None)

        Returns:
            dict: Informations détaillées de la voix

        Raises:
            Exception: Si la voix n'existe pas
        """
        pass

    @abstractmethod
    def get_user_info(self) -> dict:
        """
        Récupère les informations utilisateur (quotas, usage)

        Returns:
            dict: Informations utilisateur contenant au minimum:
                - tier: Niveau d'abonnement
                - character_count: Caractères utilisés
                - character_limit: Limite de caractères
        """
        pass

    @abstractmethod
    def test_connection(self) -> bool:
        """
        Test la connexion au service TTS

        Returns:
            bool: True si la connexion fonctionne, False sinon
        """
        pass

    @abstractmethod
    def get_narrative_voice_settings(self, style: str = "enthusiastic") -> dict:
        """
        Retourne les paramètres de voix optimisés pour un style narratif

        Args:
            style: Style de narration
                - enthusiastic: Enthousiaste et dynamique
                - calm: Calme et posé
                - dramatic: Dramatique et expressif
                - informative: Informatif et neutre

        Returns:
            dict: Paramètres de voix ou recommandations selon le service
        """
        pass

    @abstractmethod
    def generate_tourist_guide_audio(
        self,
        text: str,
        content_type: str = "attraction",
        voice_id: Optional[str] = None,
        language_label: Optional[str] = None
    ) -> bytes:
        """
        Génère un audio optimisé pour guide touristique

        Args:
            text: Texte à convertir
            content_type: Type de contenu
                - attraction: Présentation d'attraction
                - history: Récit historique
                - practical: Information pratique
                - anecdote: Anecdote
                - welcome: Message d'accueil
                - transition: Transition entre points
            voice_id: ID de la voix (optionnel)
            language_label: Nom lisible de la langue pour logs

        Returns:
            bytes: Audio optimisé
        """
        pass

    @abstractmethod
    def estimate_cost(self, text: str) -> dict:
        """
        Estime le coût de génération d'un audio

        Args:
            text: Texte à analyser

        Returns:
            dict: Estimation contenant:
                - character_count: Nombre de caractères
                - estimated_cost_usd: Coût estimé en USD
                - voice_id: Voix utilisée
                - model: Modèle utilisé
                - note: Note explicative
        """
        pass


class TTSClientFactory:
    """
    Factory pour créer des instances de clients TTS

    Usage:
        client = TTSClientFactory.create('openai')
        client = TTSClientFactory.create('elevenlabs')
    """

    _clients = {}

    @classmethod
    def register(cls, name: str, client_class):
        """
        Enregistre un nouveau type de client TTS

        Args:
            name: Nom du service (openai, elevenlabs, etc.)
            client_class: Classe du client
        """
        cls._clients[name.lower()] = client_class

    @classmethod
    def create(cls, name: str, **kwargs) -> BaseTTSClient:
        """
        Crée une instance de client TTS

        Args:
            name: Nom du service
            **kwargs: Arguments pour l'initialisation du client

        Returns:
            BaseTTSClient: Instance du client

        Raises:
            ValueError: Si le service n'est pas enregistré
        """
        client_class = cls._clients.get(name.lower())
        if not client_class:
            available = ', '.join(cls._clients.keys())
            raise ValueError(
                f"Service TTS '{name}' non disponible. "
                f"Services disponibles: {available}"
            )

        return client_class(**kwargs)

    @classmethod
    def list_available(cls) -> list:
        """
        Liste tous les services TTS disponibles

        Returns:
            list: Liste des noms de services
        """
        return list(cls._clients.keys())
