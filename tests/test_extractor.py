"""
Test per il modulo di estrazione AI (extractor.py).
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.property import PropertyData
from app.services.extractor import PropertyExtractor
from app.services.scraper import ScraperResult


def make_scraper_result(text: str = "", screenshot: str | None = None) -> ScraperResult:
    return ScraperResult(
        url="https://www.immobiliare.it/annunci/123/",
        portal="immobiliare",
        text_content=text,
        screenshot_base64=screenshot,
        success=True,
    )


def make_openai_response(data: dict) -> MagicMock:
    """Crea un mock della risposta OpenAI."""
    msg = MagicMock()
    msg.content = json.dumps(data)
    choice = MagicMock()
    choice.message = msg
    response = MagicMock()
    response.choices = [choice]
    return response


# ---------------------------------------------------------------------------
# Test: _build_property_data
# ---------------------------------------------------------------------------


def test_build_property_data_complete():
    result = make_scraper_result("Appartamento 85mq Milano 280000€")
    raw = {
        "prezzo": 280000,
        "mq": 85,
        "locali": 3,
        "camere": 2,
        "bagni": 1,
        "piano": "3° di 5",
        "ascensore": True,
        "garage": False,
        "giardino": None,
        "anno_costruzione": 1980,
        "classe_energetica": "c",
        "tipologia": "Appartamento",
        "indirizzo": "Via Roma 1",
        "citta": "Milano",
        "zona": "Navigli",
        "regione": "Lombardia",
    }
    pd_data = PropertyExtractor._build_property_data(result, raw)

    assert pd_data.prezzo == 280000.0
    assert pd_data.mq == 85.0
    assert pd_data.locali == 3
    assert pd_data.classe_energetica == "C"  # normalizzata in maiuscolo
    assert pd_data.ascensore is True
    assert pd_data.garage is False
    assert pd_data.prezzo_mq == round(280000 / 85, 2)
    assert pd_data.portal == "immobiliare"


def test_build_property_data_partial():
    """Verifica che i campi mancanti vengano gestiti con None."""
    result = make_scraper_result()
    raw = {"prezzo": "280000", "mq": None}
    pd_data = PropertyExtractor._build_property_data(result, raw)

    assert pd_data.prezzo == 280000.0
    assert pd_data.mq is None
    assert pd_data.prezzo_mq is None  # non calcolabile senza mq


def test_build_property_data_invalid_types():
    """Verifica la robustezza dei tipi con valori non validi."""
    result = make_scraper_result()
    raw = {"prezzo": "abc", "mq": "N/D", "locali": "tre"}
    pd_data = PropertyExtractor._build_property_data(result, raw)

    assert pd_data.prezzo is None
    assert pd_data.mq is None
    assert pd_data.locali is None


# ---------------------------------------------------------------------------
# Test: extract (mocked OpenAI)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_uses_text_when_sufficient():
    """Con testo sufficiente, deve usare la modalità testo (non Vision)."""
    long_text = "Appartamento trilocale 85mq Milano zona Navigli 280000€ " * 10
    result = make_scraper_result(text=long_text, screenshot="base64data")

    mock_response = make_openai_response({
        "prezzo": 280000, "mq": 85, "citta": "Milano", "locali": 3,
        "classe_energetica": "C"
    })

    extractor = PropertyExtractor()
    with patch.object(extractor._client.chat.completions, "create", AsyncMock(return_value=mock_response)):
        property_data = await extractor.extract(result)

    assert property_data.prezzo == 280000.0
    assert property_data.citta == "Milano"
    assert property_data.locali == 3


@pytest.mark.asyncio
async def test_extract_uses_vision_when_text_scarce():
    """Con testo scarso (<300 caratteri), deve usare Vision se disponibile."""
    result = make_scraper_result(text="Poco testo", screenshot="base64screenshot")

    mock_response = make_openai_response({
        "prezzo": 350000, "mq": 100, "citta": "Roma"
    })

    extractor = PropertyExtractor()
    with patch.object(extractor._client.chat.completions, "create", AsyncMock(return_value=mock_response)):
        property_data = await extractor.extract(result)

    assert property_data.prezzo == 350000.0
    assert property_data.citta == "Roma"
