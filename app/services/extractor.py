"""
Modulo di estrazione AI con GPT-4o.
Trasforma il testo grezzo dell'annuncio in un oggetto PropertyData strutturato.
"""
from __future__ import annotations

import json
from typing import Optional

from openai import AsyncOpenAI, BadRequestError
from openai.types.chat import ChatCompletion

from app.core.config import get_settings
from app.core.logging import logger
from app.models.property import PropertyData
from app.services.scraper import ScraperResult

settings = get_settings()

# ---------------------------------------------------------------------------
# Prompt di sistema
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """Sei un assistente specializzato nell'analisi di annunci immobiliari italiani.
Il tuo compito è estrarre con precisione le informazioni strutturate da testo di annunci immobiliari.

Rispondi SEMPRE e SOLO con un oggetto JSON valido, senza markdown, senza commenti.
Se un campo non è presente o non è determinabile, usa null.

Struttura JSON attesa:
{
  "prezzo": <numero float in EUR, es. 280000.0>,
  "mq": <numero float, superficie commerciale in m², es. 85.0>,
  "locali": <intero, numero di locali/vani, es. 3>,
  "camere": <intero, numero di camere da letto, es. 2>,
  "bagni": <intero, numero di bagni, es. 1>,
  "piano": <stringa, es. "3° di 5" o "piano terra">,
  "ascensore": <booleano true/false>,
  "garage": <booleano true/false>,
  "giardino": <booleano true/false>,
  "anno_costruzione": <intero, anno>,
  "classe_energetica": <stringa, una tra: "A4","A3","A2","A1","B","C","D","E","F","G">,
  "tipologia": <stringa, es. "Appartamento","Villa","Attico","Bilocale","Trilocale","Ufficio","Garage">,
  "indirizzo": <stringa, indirizzo completo o parziale>,
  "citta": <stringa, nome della città>,
  "zona": <stringa, quartiere o zona>,
  "regione": <stringa, nome della regione italiana>
}

Regole importanti:
- I prezzi devono essere numeri puri senza simboli (es. 280000 non "280.000 €")
- Le superfici devono essere in m² come numero puro
- Normalizza la classe energetica in maiuscolo
- Per le città, usa il nome ufficiale completo (es. "Milano" non "mi")
"""

USER_PROMPT_TEXT = """Analizza il seguente testo di un annuncio immobiliare ed estrai le informazioni strutturate:

---
{text_content}
---

URL annuncio: {url}
"""

USER_PROMPT_VISION = """Analizza questa pagina web di un annuncio immobiliare ed estrai le informazioni strutturate.
Osserva attentamente prezzi, superfici, caratteristiche e localizzazione visibili nell'immagine.

URL annuncio: {url}
"""


# ---------------------------------------------------------------------------
# Classe principale
# ---------------------------------------------------------------------------


class PropertyExtractor:
    """
    Estrae dati strutturati da testo/screenshot di annunci immobiliari usando GPT-4o.

    Strategia:
    1. Prova con il testo (più economico)
    2. Se il testo è troppo scarso, usa GPT-4o Vision con lo screenshot
    """

    def __init__(
        self,
        provider: str = "openai",
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> None:
        self._provider = provider
        if provider == "moonshot":
            key = api_key or settings.moonshot_api_key
            if not key:
                raise ValueError(
                    "Moonshot API key mancante. Inseriscila nelle impostazioni frontend o nel file .env"
                )
            masked = key[:4] + "..." + key[-4:]
            used_base = base_url or settings.moonshot_base_url
            logger.info("Moonshot client inizializzato | key=%s | model=%s | base_url=%s", masked, model or settings.moonshot_model, used_base)
            self._model = model or settings.moonshot_model
            self._client = AsyncOpenAI(
                api_key=key,
                base_url=used_base,
            )
        elif provider == "nvidia":
            key = api_key or settings.nvidia_api_key
            if not key:
                raise ValueError(
                    "NVIDIA API key mancante. Inseriscila nelle impostazioni frontend o nel file .env"
                )
            masked = key[:4] + "..." + key[-4:]
            used_base = base_url or settings.nvidia_base_url
            logger.info("NVIDIA client inizializzato | key=%s | model=%s | base_url=%s", masked, model or settings.nvidia_model, used_base)
            self._model = model or settings.nvidia_model
            self._client = AsyncOpenAI(
                api_key=key,
                base_url=used_base,
            )
        else:
            key = api_key or settings.openai_api_key
            if not key:
                raise ValueError(
                    "OpenAI API key mancante. Inseriscila nelle impostazioni frontend o nel file .env"
                )
            self._model = model or settings.openai_model
            self._client = AsyncOpenAI(
                api_key=key,
                base_url=base_url or None,
            )

    async def extract(self, scraper_result: ScraperResult) -> PropertyData:
        """
        Punto di ingresso principale. Riceve il risultato dello scraper
        e restituisce un oggetto PropertyData validato.
        """
        logger.info(
            "Avvio estrazione AI | provider=%s | portale=%s | testo=%d caratteri",
            self._provider,
            scraper_result.portal,
            len(scraper_result.text_content),
        )

        # Determina quale strategia usare
        use_vision = (
            len(scraper_result.text_content) < 300
            and scraper_result.screenshot_base64 is not None
        )

        if use_vision:
            logger.info("Testo insufficiente, uso GPT-4o Vision con screenshot")
            raw_data = await self._extract_with_vision(scraper_result)
        else:
            raw_data = await self._extract_with_text(scraper_result)

        # Costruisci e valida il modello Pydantic
        property_data = self._build_property_data(scraper_result, raw_data)
        logger.info(
            "Estrazione completata | prezzo=%s | mq=%s | città=%s",
            property_data.prezzo,
            property_data.mq,
            property_data.citta,
        )
        return property_data

    # ------------------------------------------------------------------
    # Estrazione via testo
    # ------------------------------------------------------------------

    async def _extract_with_text(self, result: ScraperResult) -> dict:
        """Usa il modello linguistico standard con il testo dell'annuncio."""
        user_content = USER_PROMPT_TEXT.format(
            text_content=result.text_content[:6000],
            url=result.url,
        )

        response: ChatCompletion = await self._client.chat.completions.create(
            model=self._model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0,
            max_tokens=1000,
        )

        return self._parse_response(response)

    # ------------------------------------------------------------------
    # Estrazione via Vision (screenshot)
    # ------------------------------------------------------------------

    async def _extract_with_vision(self, result: ScraperResult) -> dict:
        """Usa GPT-4o Vision passando lo screenshot della pagina."""
        assert result.screenshot_base64, "Screenshot non disponibile per Vision."

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": USER_PROMPT_VISION.format(url=result.url),
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{result.screenshot_base64}",
                            "detail": "high",
                        },
                    },
                ],
            },
        ]

        try:
            response: ChatCompletion = await self._client.chat.completions.create(
                model=self._model,
                response_format={"type": "json_object"},
                messages=messages,  # type: ignore[arg-type]
                temperature=0,
                max_tokens=1000,
            )
            return self._parse_response(response)
        except BadRequestError as e:
            logger.warning("Vision request fallita, fallback a testo: %s", e)
            return await self._extract_with_text(result)

    # ------------------------------------------------------------------
    # Parsing e costruzione del modello
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_response(response: ChatCompletion) -> dict:
        """Estrae e parsa il JSON dalla risposta del modello."""
        content = response.choices[0].message.content or "{}"
        try:
            data = json.loads(content)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError as e:
            logger.error("Errore parsing JSON GPT-4o: %s | contenuto: %s", e, content[:500])
            return {}

    @staticmethod
    def _build_property_data(result: ScraperResult, raw_data: dict) -> PropertyData:
        """
        Costruisce l'oggetto PropertyData validato da Pydantic
        combinando i dati estratti con i metadati dello scraper.
        """
        # Sanity check sui tipi numerici
        def safe_float(val) -> Optional[float]:
            try:
                return float(val) if val is not None else None
            except (TypeError, ValueError):
                return None

        def safe_int(val) -> Optional[int]:
            try:
                return int(val) if val is not None else None
            except (TypeError, ValueError):
                return None

        def safe_bool(val) -> Optional[bool]:
            if val is None:
                return None
            if isinstance(val, bool):
                return val
            if isinstance(val, str):
                return val.lower() in ("true", "si", "sì", "yes", "1")
            return bool(val)

        return PropertyData(
            url=result.url,
            portal=result.portal,
            prezzo=safe_float(raw_data.get("prezzo")),
            mq=safe_float(raw_data.get("mq")),
            locali=safe_int(raw_data.get("locali")),
            camere=safe_int(raw_data.get("camere")),
            bagni=safe_int(raw_data.get("bagni")),
            piano=raw_data.get("piano"),
            ascensore=safe_bool(raw_data.get("ascensore")),
            garage=safe_bool(raw_data.get("garage")),
            giardino=safe_bool(raw_data.get("giardino")),
            anno_costruzione=safe_int(raw_data.get("anno_costruzione")),
            classe_energetica=(raw_data.get("classe_energetica") or "").upper() or None,
            tipologia=raw_data.get("tipologia"),
            indirizzo=raw_data.get("indirizzo"),
            citta=raw_data.get("citta"),
            zona=raw_data.get("zona"),
            regione=raw_data.get("regione"),
            descrizione_raw=result.text_content[:2000] if result.text_content else None,
        )
