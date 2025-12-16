"""
OpenAI Language Client
 - Batch translations
 - Marketing tour name generation
"""
import json
import os
import time
from typing import List, Dict, Optional

import requests

LANGUAGE_LABELS = {
    "en": "English",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "de": "German",
    "pt": "Portuguese (Portugal)"  # Force explicit EU Portuguese wording
}

LANGUAGE_VARIANT_HINTS = {
    "pt": (
        "When handling Portuguese outputs, always use the European Portuguese "
        "(Portugal) variant. Avoid Brazilian vocabulary or spelling."
    )
}


class OpenAILanguageClient:
    def __init__(
        self,
        model: Optional[str] = None,
        timeout: int = 60,
        max_retries: int = 3,
    ):
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY manquante dans l'environnement")

        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.timeout = timeout
        self.max_retries = max_retries
        self.base_url = "https://api.openai.com/v1/chat/completions"
        self.session = requests.Session()

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #
    def translate_batch(
        self,
        texts: List[str],
        target_language: str,
        source_language: Optional[str] = "en",
    ) -> List[str]:
        """
        Traduit une liste de textes en respectant l'ordre fourni.
        """
        if not texts:
            return []

        target_label = LANGUAGE_LABELS.get(target_language, target_language)
        source_label = LANGUAGE_LABELS.get(source_language, source_language) if source_language else None

        numbered_items = [
            {"index": idx, "text": text or ""}
            for idx, text in enumerate(texts)
        ]

        system_prompt = (
            "You are a professional translator. "
            "Each input string is the name of a tourist place or guided tour. "
            "Preserve the local/marketing tone and return only valid JSON."
        )
        variant_hint = LANGUAGE_VARIANT_HINTS.get(target_language.lower())
        if variant_hint:
            system_prompt += " " + variant_hint

        if source_label:
            user_intro = (
                f"Translate the following names from {source_label} to {target_label}. "
                "Each name represents a tourist attraction or a guided tour. "
                "Keep the cultural meaning and do not add extra text.\n"
                "Respond ONLY with a JSON array of strings in the same order "
                "as the inputs.\n\n"
            )
        else:
            user_intro = (
                "The texts below may be in different languages. "
                f"Translate them into {target_label}. "
                "Each name represents a tourist attraction or guided tour. "
                "Keep the cultural meaning and do not add extra text.\n"
                "Respond ONLY with a JSON array of strings in the same order "
                "as the inputs.\n\n"
            )

        user_prompt = user_intro + f"{json.dumps(numbered_items, ensure_ascii=False, indent=2)}"

        content = self._chat_completion(
            system_prompt,
            user_prompt,
            temperature=0.2,
            max_tokens=600,
        )

        translations = self._parse_json_array(content, expected_len=len(texts))
        if translations is None:
            raise RuntimeError(
                f"Traduction OpenAI échouée (langue cible={target_label}) – "
                "réponse vide ou invalide."
            )

        # S'assurer que la taille correspond
        if len(translations) != len(texts):
            raise RuntimeError(
                f"Traduction OpenAI incomplète (attendu {len(texts)} éléments, "
                f"reçu {len(translations)} pour langue cible={target_label})."
            )

        return [t.strip() if isinstance(t, str) else original
                for t, original in zip(translations, texts)]

    def generate_tour_name(
        self,
        city: str,
        country: str,
        points: List[Dict[str, str]],
    ) -> Optional[str]:
        """
        Génère un nom marketing court pour un tour (EN).
        """
        if not points:
            return None

        points_preview = [
            {"name": p.get("name", ""), "types": p.get("types", [])}
            for p in points[:12]
        ]

        system_prompt = (
            "You are a concise travel copywriter. Return ONLY a short, clear tour name in English "
            "and in Title Case (1–3 words, ≤25 characters), no explanations. Avoid marketing fluff "
            "and overused words such as Odyssey, Journey, Trail, Trek, Quest, Gems, Treasures, "
            "Secrets, Heritage, Epic, Ultimate, Adventure. Aim for descriptive, grounded names."
        )
        user_prompt = (
            f"City: {city}, Country: {country}\n"
            f"Points of interest:\n{json.dumps(points_preview, ensure_ascii=False, indent=2)}\n\n"
            "Create ONE original, concise tour name. Output MUST be in ENGLISH only.\n\n"
            "Requirements:\n"
            "- 1–3 words, ≤25 characters, Title Case\n"
            "- Plain, descriptive, not grandiose; avoid Odyssey/Journey/Trail/Trek/Quest/etc.\n"
            "- No quotes, no extra text, no punctuation except spaces\n\n"
            "Style examples (stay even simpler):\n"
            "- Riverfront Landmarks\n"
            "- Old Town Highlights\n"
            "- Waterfront Icons\n"
            "- Market Squares\n"
            "- Colonial Heritage"
        )

        content = self._chat_completion(
            system_prompt,
            user_prompt,
            temperature=0.6,
            max_tokens=32,
        )

        if not content:
            return None

        name = content.strip().split("\n")[0].strip().strip('"').strip("'")
        if not name:
            return None

        normalized = " ".join(name.split())
        words = normalized.split()
        if len(words) > 4:
            normalized = " ".join(words[:4])

        # Limiter à 40 chars comme demandé
        return normalized[:40] if normalized else None

    # --------------------------------------------------------------------- #
    # Helpers
    # --------------------------------------------------------------------- #
    def _chat_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        for attempt in range(self.max_retries):
            try:
                response = self.session.post(
                    self.base_url,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout,
                )
                if response.status_code == 200:
                    data = response.json()
                    choices = data.get("choices", [])
                    if choices:
                        return choices[0]["message"]["content"]
                    return ""

                if response.status_code in (429, 500, 503):
                    wait_time = 2 ** attempt
                    print(f"⏳ OpenAI rate limit/erreur ({response.status_code}), "
                          f"attente {wait_time}s...")
                    time.sleep(wait_time)
                    continue

                print(f"❌ Erreur OpenAI {response.status_code}: {response.text}")
                break

            except requests.RequestException as exc:
                wait_time = 2 ** attempt
                print(f"⚠️ Exception OpenAI: {exc} (tentative {attempt+1}), "
                      f"attente {wait_time}s")
                time.sleep(wait_time)

        return ""

    @staticmethod
    def _parse_json_array(content: str, expected_len: int) -> Optional[List[str]]:
        if not content:
            return None

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        start = content.find("[")
        end = content.rfind("]")
        if start != -1 and end != -1:
            try:
                return json.loads(content[start:end + 1])
            except json.JSONDecodeError:
                return None

        return None
