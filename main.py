"""
Narrando V2 CLI – lance tout le pipeline (génération EN + traduction) en local.
"""
import argparse
import sys
import time
from typing import Optional

from clients.google_maps_client import GoogleMapsClient
from api import narrando_api


def resolve_place_id(city: str, country: str) -> str:
    """Utilise Google pour retrouver le place_id correspondant à ville/pays."""
    google_client = GoogleMapsClient()
    info = google_client.get_city_info(city, country)
    place_id = info.get("place_id")
    if not place_id:
        raise ValueError(
            f"Impossible de trouver le place_id pour '{city}, {country}'. "
            "Vérifie l'orthographe ou fournis --place-id."
        )

    print(f"✅ Ville trouvée : {info.get('formatted_address', city)}")
    print(f"   🆔 place_id    : {place_id}")
    print(f"   🌍 ISO         : {info.get('country_iso_code')}")
    return place_id


def run_pipeline(
    place_id: str,
    skip_audio: bool,
    skip_descriptions: bool,
) -> dict:
    """Wrap autour NarrandoAPI pour lancer la génération complète."""
    return narrando_api.generate_tour_from_place_id(
        place_id=place_id,
        skip_audio=skip_audio,
        skip_descriptions=skip_descriptions,
    )


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Narrando V2 – génération de tours (golden EN + traductions)"
    )
    parser.add_argument("--place-id", help="Place ID Google (prioritaire s'il est fourni)")
    parser.add_argument("--ville", "-v", help="Nom de la ville (utile si pas de place_id)")
    parser.add_argument("--pays", "-p", help="Nom du pays (utile si pas de place_id)")
    parser.add_argument("--skip-audio", action="store_true", help="Ne pas générer les audios")
    parser.add_argument(
        "--skip-descriptions", action="store_true", help="Ne pas générer les descriptions (phase audio)"
    )

    args = parser.parse_args(argv)

    try:
        start = time.time()
        place_id = args.place_id

        if not place_id:
            if not args.ville or not args.pays:
                parser.error("Fournis soit --place-id, soit --ville et --pays.")
            place_id = resolve_place_id(args.ville, args.pays)
        else:
            print(f"🆔 place_id fourni : {place_id}")

        print("\n🚀 Lancement NarrandoAPI.generate_tour_from_place_id ...")
        result = run_pipeline(
            place_id=place_id,
            skip_audio=args.skip_audio,
            skip_descriptions=args.skip_descriptions,
        )
        elapsed = time.time() - start

        tours = result.get("tours", [])
        print("\n🎉 Génération terminée")
        print(f"   🏙️ Ville          : {result.get('city')}")
        print(f"   🇺🇸 Golden record  : EN")
        print(f"   🎪 Tours créés     : {len(tours)}")
        print(f"   📍 Total points    : {result.get('point_count', 'n/a')}")
        print(f"   ⏱️ Temps total     : {elapsed:.2f}s")
        print("   🌐 Traductions     : ", ", ".join(getattr(narrando_api, "translation_languages", [])))

        return 0

    except Exception as exc:
        print(f"❌ Erreur: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
