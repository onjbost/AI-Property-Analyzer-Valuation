"""
Test per il modulo di analisi qualitativa AI (sentiment_analyzer.py).
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.property import PropertyData, SentimentAnalysis
from app.services.sentiment_analyzer import PropertySentimentAnalyzer


def make_property_data() -> PropertyData:
    return PropertyData(
        url="https://www.immobiliare.it/annunci/123/",
        portal="immobiliare",
        prezzo=280000,
        mq=85,
        citta="Milano",
        zona="Navigli",
        locali=3,
        camere=2,
        bagni=1,
        piano="3° di 5",
        ascensore=True,
        garage=False,
        giardino=False,
        anno_costruzione=1980,
        classe_energetica="C",
        tipologia="Appartamento",
        indirizzo="Via Roma 1",
        regione="Lombardia",
        descrizione_raw="Appartamento luminoso con vista sul parco, appena ristrutturato. Mancanza di posto auto.",
    )


def make_scraper_result():
    from app.services.scraper import ScraperResult
    return ScraperResult(
        url="https://www.immobiliare.it/annunci/123/",
        portal="immobiliare",
        text_content="Appartamento luminoso con vista sul parco...",
        screenshot_base64=None,
        success=True,
    )


def make_openai_response(data: dict) -> MagicMock:
    msg = MagicMock()
    msg.content = json.dumps(data)
    choice = MagicMock()
    choice.message = msg
    response = MagicMock()
    response.choices = [choice]
    return response


@pytest.mark.asyncio
async def test_analyze_extracts_strengths_and_weaknesses():
    """Deve estrarre correttamente punti di forza e deboli dalla risposta AI."""
    prop = make_property_data()
    scraper = make_scraper_result()

    mock_response = make_openai_response({
        "strengths": [
            {"description": "Vista parco", "price_impact_percent": 8.0},
            {"description": "Ristrutturato recentemente", "price_impact_percent": 10.0},
        ],
        "weaknesses": [
            {"description": "Mancanza posto auto", "price_impact_percent": -5.0},
        ],
    })

    analyzer = PropertySentimentAnalyzer()
    with patch.object(analyzer._client.chat.completions, "create", AsyncMock(return_value=mock_response)):
        result = await analyzer.analyze(prop, scraper)

    assert isinstance(result, SentimentAnalysis)
    assert len(result.strengths) == 2
    assert len(result.weaknesses) == 1
    assert result.strengths[0].description == "Vista parco"
    assert result.strengths[0].price_impact_percent == 8.0
    assert result.weaknesses[0].price_impact_percent == -5.0


@pytest.mark.asyncio
async def test_analyze_returns_empty_on_api_error():
    """Se l'API fallisce, deve restituire un oggetto vuoto senza sollevare eccezioni."""
    prop = make_property_data()
    scraper = make_scraper_result()

    analyzer = PropertySentimentAnalyzer()
    with patch.object(analyzer._client.chat.completions, "create", AsyncMock(side_effect=Exception("API Error"))):
        result = await analyzer.analyze(prop, scraper)

    assert isinstance(result, SentimentAnalysis)
    assert len(result.strengths) == 0
    assert len(result.weaknesses) == 0


@pytest.mark.asyncio
async def test_analyze_limits_to_five_items():
    """Deve limitare a max 5 item per categoria anche se l'AI ne restituisce di più."""
    prop = make_property_data()
    scraper = make_scraper_result()

    mock_response = make_openai_response({
        "strengths": [
            {"description": f"Forza {i}", "price_impact_percent": float(i)}
            for i in range(10)
        ],
        "weaknesses": [],
    })

    analyzer = PropertySentimentAnalyzer()
    with patch.object(analyzer._client.chat.completions, "create", AsyncMock(return_value=mock_response)):
        result = await analyzer.analyze(prop, scraper)

    assert len(result.strengths) == 5
