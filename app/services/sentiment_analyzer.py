"""
Modulo di analisi qualitativa AI per annunci immobiliari.
Estrae punti di forza e deboli con impatto percentuale sul prezzo.
"""
from __future__ import annotations

import json
from typing import Optional

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion

from app.core.config import get_settings
from app.core.logging import logger
from app.models.property import PropertyData, SentimentAnalysis, SentimentItem
from app.services.scraper import ScraperResult

settings = get_settings()

# ---------------------------------------------------------------------------
# Prompt di sistema
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """Sei un esperto analista immobiliare italiano.
Il tuo compito è analizzare un annuncio immobiliare e identificare i punti di forza e i punti deboli che influenzano il valore di mercato dell'immobile.

Rispondi SEMPRE e SOLO con un oggetto JSON valido, senza markdown, senza commenti.

Struttura JSON attesa:
{
  "strengths": [
    {"description": "...", "price_impact_percent": <float>},
    ...
  ],
  "weaknesses": [
    {"description": "...", "price_impact_percent": <float>},
    ...
  ]
}

Regole importanti:
- Lista max 5 punti di forza e max 5 punti deboli.
- Ogni punto deve avere un impatto percentuale REALISTICO sul prezzo totale dell'immobile.
- Gli impatti sono percentuali relative al PREZZO TOTALE (non al mq).
- Esempi realistici: vista mare +10-15%, ristrutturazione recente +8-12%, garage incluso +5-8%, mancanza ascensore in palazzo alto -5-8%, zona rumorosa -5-10%, servizi lontani -3-7%.
- Se un dato è già catturato nei dati strutturati (es. "garage: true"), NON ripeterlo come punto di forza a meno che non ci sia un valore aggiunto specifico (es. "garage doppio in centro").
- Cerca di individuare aspetti QUALITATIVI emergenti dalla descrizione testuale, non ovvi dai dati strutturati.
- Se non ci sono punti rilevanti, usa liste vuote.
- La somma degli impatti positivi e negativi deve essere ragionevole (tipicamente tra -30% e +30% in totale).
"""

USER_PROMPT = """Analizza l'annuncio immobiliare seguente ed estrai punti di forza e deboli.

--- DATI STRUTTURATI DELL'IMMOBILE ---
Prezzo: {prezzo} €
Superficie: {mq} m²
Tipologia: {tipologia}
Locali: {locali}
Camere: {camere}
Bagni: {bagni}
Piano: {piano}
Ascensore: {ascensore}
Garage/Posto auto: {garage}
Giardino/Terrazzo: {giardino}
Anno costruzione: {anno_costruzione}
Classe energetica: {classe_energetica}
Città: {citta}
Zona: {zona}
Indirizzo: {indirizzo}

--- DESCRIZIONE TESTUALE DELL'ANNUNCIO ---
{descrizione}

--- URL ---
{url}
"""


class PropertySentimentAnalyzer:
    """
    Analizza qualitativamente un annuncio immobiliare usando un LLM.
    Restituisce punti di forza/deboli con impatto percentuale sul prezzo.
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
            used_base = base_url or settings.moonshot_base_url
            self._model = model or settings.moonshot_model
            self._client = AsyncOpenAI(api_key=key, base_url=used_base)
        elif provider == "nvidia":
            key = api_key or settings.nvidia_api_key
            used_base = base_url or settings.nvidia_base_url
            self._model = model or settings.nvidia_model
            self._client = AsyncOpenAI(api_key=key, base_url=used_base)
        else:
            key = api_key or settings.openai_api_key
            self._model = model or settings.openai_model
            self._client = AsyncOpenAI(api_key=key, base_url=base_url or None)

    async def analyze(self, property_data: PropertyData, scraper_result: ScraperResult) -> SentimentAnalysis:
        """
        Esegue l'analisi qualitativa dell'annuncio.
        Se la chiamata AI fallisce, restituisce un oggetto vuoto per non bloccare il report.
        """
        logger.info("Avvio analisi qualitativa | provider=%s | model=%s", self._provider, self._model)

        user_content = USER_PROMPT.format(
            prezzo=property_data.prezzo or "N/D",
            mq=property_data.mq or "N/D",
            tipologia=property_data.tipologia or "N/D",
            locali=property_data.locali or "N/D",
            camere=property_data.camere or "N/D",
            bagni=property_data.bagni or "N/D",
            piano=property_data.piano or "N/D",
            ascensore="Sì" if property_data.ascensore else ("No" if property_data.ascensore is False else "N/D"),
            garage="Sì" if property_data.garage else ("No" if property_data.garage is False else "N/D"),
            giardino="Sì" if property_data.giardino else ("No" if property_data.giardino is False else "N/D"),
            anno_costruzione=property_data.anno_costruzione or "N/D",
            classe_energetica=property_data.classe_energetica or "N/D",
            citta=property_data.citta or "N/D",
            zona=property_data.zona or "N/D",
            indirizzo=property_data.indirizzo or "N/D",
            descrizione=(property_data.descrizione_raw or "")[:4000],
            url=property_data.url,
        )

        try:
            response: ChatCompletion = await self._client.chat.completions.create(
                model=self._model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.2,
                max_tokens=1500,
            )

            raw = self._parse_response(response)
            return self._build_sentiment_analysis(raw)
        except Exception as exc:
            logger.warning("Analisi qualitativa fallita, restituisco risultato vuoto: %s", exc)
            return SentimentAnalysis()

    @staticmethod
    def _parse_response(response: ChatCompletion) -> dict:
        """Estrae e parsa il JSON dalla risposta del modello."""
        content = response.choices[0].message.content or "{}"
        try:
            data = json.loads(content)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError as e:
            logger.error("Errore parsing JSON sentiment: %s | contenuto: %s", e, content[:500])
            return {}

    @staticmethod
    def _build_sentiment_analysis(raw_data: dict) -> SentimentAnalysis:
        """Costruisce l'oggetto SentimentAnalysis validato da Pydantic."""

        def parse_items(items: list | None) -> list[SentimentItem]:
            if not items:
                return []
            result = []
            for item in items[:5]:
                if not isinstance(item, dict):
                    continue
                desc = item.get("description")
                impact = item.get("price_impact_percent")
                if desc and isinstance(impact, (int, float)):
                    result.append(SentimentItem(description=str(desc), price_impact_percent=float(impact)))
            return result

        strengths = parse_items(raw_data.get("strengths"))
        weaknesses = parse_items(raw_data.get("weaknesses"))

        logger.info(
            "Analisi qualitativa completata | strengths=%d | weaknesses=%d",
            len(strengths),
            len(weaknesses),
        )
        return SentimentAnalysis(strengths=strengths, weaknesses=weaknesses)
