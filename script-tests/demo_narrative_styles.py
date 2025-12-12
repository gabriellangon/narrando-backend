#!/usr/bin/env python3
"""
Démonstration des styles narratifs ElevenLabs pour guides touristiques
"""
import os
from dotenv import load_dotenv

load_dotenv()

def demo_narrative_styles():
    """Démonstration des différents styles narratifs"""
    
    print("🎭 Démonstration des Styles Narratifs ElevenLabs")
    print("=" * 60)
    
    try:
        from clients.elevenlabs_client import ElevenLabsClient
        
        client = ElevenLabsClient()
        
        if not client.client:
            print("❌ Client ElevenLabs non configuré")
            print("💡 Vérifiez votre ELEVENLABS_API_KEY dans .env")
            return
        
        # Textes de test pour différents contextes
        sample_texts = {
            "attraction": """
            Bienvenue devant la Tour Eiffel ! Cette merveille d'ingénierie de 330 mètres 
            de haut a été construite par Gustave Eiffel pour l'Exposition universelle de 1889. 
            Saviez-vous qu'elle était initialement prévue pour être démontée après 20 ans ? 
            Aujourd'hui, elle accueille plus de 7 millions de visiteurs par an !
            """,
            
            "history": """
            Laissez-moi vous raconter une anecdote fascinante... En 1944, quand les Alliés 
            approchaient de Paris, Hitler avait ordonné la destruction de tous les monuments 
            de la capitale, y compris la Tour Eiffel. Mais le général von Choltitz a refusé 
            d'exécuter cet ordre, sauvant ainsi notre Dame de Fer bien-aimée !
            """,
            
            "practical": """
            Informations pratiques : La Tour Eiffel est ouverte tous les jours de 9h30 à 23h45. 
            Les tarifs varient de 29,40€ pour l'accès au sommet par ascenseur à 11,80€ pour 
            le deuxième étage par escalier. Je recommande de réserver en ligne pour éviter 
            les longues files d'attente.
            """,
            
            "anecdote": """
            Voici une histoire incroyable que peu connaissent... En 1912, un tailleur autrichien 
            nommé Franz Reichelt était convaincu d'avoir inventé un parachute révolutionnaire. 
            Il grimpa au premier étage de la Tour Eiffel et... sauta ! Malheureusement, 
            son invention ne fonctionna pas. Cette tragédie reste l'un des événements 
            les plus marquants de l'histoire de notre tour !
            """
        }
        
        print("🎙️ Configuration actuelle:")
        print(f"   Voix: {client.voice_id}")
        
        # Test de connection
        if not client.test_connection():
            print("❌ Impossible de se connecter à ElevenLabs")
            return
        
        print("\n🎵 Styles narratifs disponibles:")
        
        # Afficher tous les styles disponibles
        for style_name in ["enthusiastic", "calm", "dramatic", "informative"]:
            style_info = client.get_narrative_voice_settings(style_name)
            print(f"   • {style_name.upper()}: {style_info['description']}")
            print(f"     Paramètres: stability={style_info['stability']}, style={style_info['style']}")
        
        print("\n" + "=" * 60)
        
        # Démonstration de chaque type de contenu
        for content_type, text in sample_texts.items():
            print(f"\n📖 CONTENU: {content_type.upper()}")
            print("-" * 40)
            
            # Obtenir les paramètres pour ce type de contenu
            content_to_style = {
                "attraction": "enthusiastic",
                "history": "dramatic", 
                "practical": "informative",
                "anecdote": "dramatic"
            }
            
            style = content_to_style[content_type]
            settings = client.get_narrative_voice_settings(style)
            
            print(f"🎭 Style utilisé: {style}")
            print(f"📝 Description: {settings['description']}")
            print(f"⚙️  Paramètres:")
            print(f"   - Stability: {settings['stability']} (expressivité)")
            print(f"   - Style: {settings['style']} (émotion)")
            print(f"   - Similarity: {settings['similarity_boost']} (identité voix)")
            
            # Estimation du coût
            cost = client.estimate_cost(text)
            print(f"💰 Coût estimé: ${cost['estimated_cost_usd']} ({cost['character_count']} caractères)")
            
            # Option de génération réelle (décommentez pour tester)
            print("🔇 Génération audio désactivée (décommentez pour tester réellement)")
            # try:
            #     audio_data = client.generate_tourist_guide_audio(text, content_type)
            #     print(f"✅ Audio généré: {len(audio_data)} bytes")
            #     
            #     # Sauvegarder pour test
            #     filename = f"demo_{content_type}_{style}.mp3"
            #     with open(f"data/audio/{filename}", 'wb') as f:
            #         f.write(audio_data)
            #     print(f"💾 Sauvegardé: data/audio/{filename}")
            # except Exception as e:
            #     print(f"❌ Erreur génération: {e}")
        
        print("\n" + "=" * 60)
        print("🎯 Comment utiliser dans votre API:")
        print("""
# Génération avec style automatique selon le contenu
audio_data = client.generate_tourist_guide_audio(text, "attraction")  # Style: enthusiastic
audio_data = client.generate_tourist_guide_audio(text, "history")     # Style: dramatic
audio_data = client.generate_tourist_guide_audio(text, "practical")   # Style: informative
audio_data = client.generate_tourist_guide_audio(text, "anecdote")    # Style: dramatic

# Ou spécifier directement le style
settings = client.get_narrative_voice_settings("enthusiastic")
audio_data = client.generate_audio(text, settings)
        """)
        
        print("🚀 Pour tester avec de vrais audios:")
        print("   1. Décommentez les lignes de génération dans ce script")
        print("   2. Créez le dossier: mkdir -p data/audio") 
        print("   3. Relancez: python demo_narrative_styles.py")
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("💡 Solution: pip install elevenlabs==2.14.0")
        
    except Exception as e:
        print(f"❌ Erreur: {e}")

def recommend_voice_for_tourism():
    """Recommandations de voix pour le tourisme"""
    
    print("\n" + "=" * 60)
    print("🎙️ RECOMMANDATIONS DE VOIX POUR GUIDES TOURISTIQUES")
    print("=" * 60)
    
    recommendations = {
        "Français": {
            "Homme": [
                ("Antoine", "Voix masculine française chaleureuse"),
                ("Thomas", "Voix grave et posée, parfaite pour l'histoire"),
                ("Fabien", "Voix énergique pour attractions")
            ],
            "Femme": [
                ("Charlotte", "Voix féminine française élégante"),
                ("Sophie", "Voix douce et claire"),
                ("Marie", "Voix expressive et enthousiaste")
            ]
        },
        "Anglais": [
            ("George", "JBFqnCBsd6RMkjVDRZzb", "Voix masculine britannique (défaut actuel)"),
            ("Charlotte", "XB0fDUnXU5powFXDhCwa", "Voix féminine énergique"),
            ("Daniel", "onwK4e9ZLuTAKqWW03F9", "Voix masculine américaine")
        ]
    }
    
    print("🇫🇷 Pour des guides en français:")
    print("   IMPORTANT: Vous devez créer/cloner des voix françaises dans ElevenLabs")
    print("   Les voix par défaut sont principalement en anglais")
    
    print("\n🇺🇸 Voix anglaises recommandées (disponibles par défaut):")
    for name, voice_id, desc in recommendations["Anglais"]:
        print(f"   • {name} ({voice_id})")
        print(f"     {desc}")
        if voice_id == "JBFqnCBsd6RMkjVDRZzb":
            print("     ✅ C'est votre voix actuelle !")
        print()
    
    print("💡 Pour changer de voix:")
    print(f"   Modifiez ELEVENLABS_VOICE_ID dans votre .env")
    print(f"   Voix actuelle: {os.getenv('ELEVENLABS_VOICE_ID', 'JBFqnCBsd6RMkjVDRZzb')}")


if __name__ == "__main__":
    # Configuration actuelle
    print(f"🔑 ELEVENLABS_API_KEY: {'✅ Définie' if os.getenv('ELEVENLABS_API_KEY') else '❌ Non définie'}")
    print(f"🎙️ ELEVENLABS_VOICE_ID: {os.getenv('ELEVENLABS_VOICE_ID', 'JBFqnCBsd6RMkjVDRZzb (défaut)')}")
    
    demo_narrative_styles()
    recommend_voice_for_tourism()