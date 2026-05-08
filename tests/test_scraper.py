"""
Test per il modulo scraper.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.scraper import PropertyScraper, ScraperResult, detect_portal


# ---------------------------------------------------------------------------
# Test: detect_portal
# ---------------------------------------------------------------------------


def test_detect_portal_immobiliare():
    url = "https://www.immobiliare.it/annunci/123456789/"
    assert detect_portal(url) == "immobiliare"


def test_detect_portal_idealista():
    url = "https://www.idealista.it/immobile/12345678/"
    assert detect_portal(url) == "idealista"


def test_detect_portal_unknown():
    url = "https://www.casa.it/annunci/123/"
    assert detect_portal(url) == "default"


def test_detect_portal_idealista_com():
    url = "https://www.idealista.com/en/immobile/12345678/"
    assert detect_portal(url) == "idealista"


# ---------------------------------------------------------------------------
# Test: ScraperResult
# ---------------------------------------------------------------------------


def test_scraper_result_defaults():
    result = ScraperResult(
        url="https://example.com",
        portal="default",
        text_content="Test content",
    )
    assert result.success is True
    assert result.error is None
    assert result.screenshot_base64 is None
    assert result.metadata == {}


def test_scraper_result_failure():
    result = ScraperResult(
        url="https://example.com",
        portal="default",
        text_content="",
        success=False,
        error="Timeout exceeded",
    )
    assert result.success is False
    assert result.error == "Timeout exceeded"


# ---------------------------------------------------------------------------
# Test: scrape_property (mocked)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scrape_property_success():
    """Verifica che lo scraper ritorni un risultato valido con browser mockato."""
    mock_page = AsyncMock()
    mock_page.goto = AsyncMock()
    mock_page.title = AsyncMock(return_value="Test Annuncio")
    mock_page.inner_text = AsyncMock(return_value="Appartamento 3 locali 85mq Milano 280000€")
    mock_page.screenshot = AsyncMock(return_value=b"fake_screenshot_bytes")
    mock_page.evaluate = AsyncMock(return_value="Mozilla/5.0 ...")
    mock_page.close = AsyncMock()

    mock_locator = AsyncMock()
    mock_locator.first = AsyncMock()
    mock_locator.first.is_visible = AsyncMock(return_value=True)
    mock_locator.first.inner_text = AsyncMock(
        return_value="Appartamento 3 locali 85mq Milano 280000€ " * 20
    )
    mock_page.locator = MagicMock(return_value=mock_locator)

    mock_context = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_context.route = AsyncMock()
    mock_context.close = AsyncMock()

    mock_browser = AsyncMock()
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_browser.close = AsyncMock()

    with patch("app.services.scraper.async_playwright") as mock_pw:
        mock_playwright_instance = AsyncMock()
        mock_playwright_instance.chromium.launch = AsyncMock(return_value=mock_browser)
        mock_playwright_instance.stop = AsyncMock()
        mock_pw.return_value.__aenter__ = AsyncMock(return_value=mock_playwright_instance)
        mock_pw.return_value.__aexit__ = AsyncMock(return_value=None)

        scraper = PropertyScraper()
        scraper._playwright = mock_playwright_instance
        scraper._browser = mock_browser

        result = await scraper._scrape_once(
            "https://www.immobiliare.it/annunci/123/", "immobiliare"
        )

    assert result.success is True
    assert result.portal == "immobiliare"
    assert len(result.text_content) > 0
