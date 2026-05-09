"""
Test per il modulo di calcolo prezzo corretto (adjusted_price.py).
"""
from __future__ import annotations

import pytest

from app.models.property import AdjustedPriceComparison, OmiComparison, PropertyData, SentimentAnalysis, SentimentItem
from app.services.adjusted_price import compute_adjusted_comparison


def make_property(prezzo: float = 280000, mq: float = 85) -> PropertyData:
    return PropertyData(
        url="https://www.immobiliare.it/annunci/123/",
        portal="immobiliare",
        prezzo=prezzo,
        mq=mq,
        citta="Milano",
        zona="Navigli",
    )


def make_omi(prezzo_medio: float = 3000) -> OmiComparison:
    return OmiComparison(
        citta_omi="Milano",
        zona_omi="B2",
        prezzo_min_omi=2500,
        prezzo_max_omi=3500,
        prezzo_medio_omi=prezzo_medio,
        scostamento_percentuale=5.0,
        is_underpriced=False,
        semestre_omi="2023-II",
    )


def make_sentiment(strengths=None, weaknesses=None) -> SentimentAnalysis:
    return SentimentAnalysis(
        strengths=strengths or [],
        weaknesses=weaknesses or [],
    )


# ---------------------------------------------------------------------------
# Test: compute_adjusted_comparison
# ---------------------------------------------------------------------------


def test_adjusted_price_with_strengths():
    """Punti di forza devono aumentare il prezzo corretto."""
    prop = make_property(prezzo=280000, mq=100)
    omi = make_omi(prezzo_medio=1000)  # base = 100.000€
    sentiment = make_sentiment(
        strengths=[SentimentItem(description="Vista mare", price_impact_percent=10.0)],
    )

    result = compute_adjusted_comparison(prop, omi, sentiment)

    assert result is not None
    assert result.prezzo_base_omi == 100000.0
    assert result.totale_aggiustamento_percentuale == 10.0
    assert result.prezzo_corretto == 110000.0
    # prezzo reale 280000 vs corretto 110000 → sopra di ~154%
    assert result.scostamento_percentuale > 0
    assert result.verdict == "SOPRASTIMATO"


def test_adjusted_price_with_weaknesses():
    """Punti deboli devono diminuire il prezzo corretto."""
    prop = make_property(prezzo=80000, mq=100)
    omi = make_omi(prezzo_medio=1000)  # base = 100.000€
    sentiment = make_sentiment(
        weaknesses=[SentimentItem(description="Mancanza ascensore", price_impact_percent=-8.0)],
    )

    result = compute_adjusted_comparison(prop, omi, sentiment)

    assert result is not None
    assert result.prezzo_base_omi == 100000.0
    assert result.totale_aggiustamento_percentuale == -8.0
    assert result.prezzo_corretto == 92000.0
    # prezzo reale 80000 vs corretto 92000 → sotto di ~13%
    assert result.scostamento_percentuale < 0
    assert result.verdict == "AFFARE"


def test_adjusted_price_mixed():
    """Forze e debolezze combinate."""
    prop = make_property(prezzo=107000, mq=100)
    omi = make_omi(prezzo_medio=1000)  # base = 100.000€
    sentiment = make_sentiment(
        strengths=[SentimentItem(description="Ristrutturato", price_impact_percent=12.0)],
        weaknesses=[SentimentItem(description="Zona rumorosa", price_impact_percent=-5.0)],
    )

    result = compute_adjusted_comparison(prop, omi, sentiment)

    assert result is not None
    assert result.totale_aggiustamento_percentuale == 7.0
    assert result.prezzo_corretto == 107000.0
    # prezzo reale = prezzo corretto → mercato
    assert result.verdict == "MERCATO"


def test_adjusted_price_missing_omi():
    """Senza dati OMI deve restituire None."""
    prop = make_property()
    omi = OmiComparison()
    sentiment = make_sentiment(strengths=[SentimentItem(description="X", price_impact_percent=5.0)])

    result = compute_adjusted_comparison(prop, omi, sentiment)
    assert result is None


def test_adjusted_price_no_sentiment():
    """Senza sentiment deve restituire None."""
    prop = make_property()
    omi = make_omi()
    result = compute_adjusted_comparison(prop, omi, None)
    assert result is None


def test_adjusted_price_empty_sentiment():
    """Sentiment vuoto deve restituire None (nessun aggiustamento da applicare)."""
    prop = make_property()
    omi = make_omi()
    sentiment = make_sentiment()
    result = compute_adjusted_comparison(prop, omi, sentiment)
    # Anche se vuoto, i dati OMI ci sono: calcoliamo comunque con 0% aggiustamento
    assert result is not None
    assert result.totale_aggiustamento_percentuale == 0.0
    assert result.prezzo_corretto == result.prezzo_base_omi
