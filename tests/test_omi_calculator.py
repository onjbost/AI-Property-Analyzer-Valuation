"""
Test per il modulo di calcolo OMI.
"""
from __future__ import annotations

import pytest

from app.models.property import EvaluationReport, PropertyData
from app.services.omi_calculator import (
    _compute_investment_score,
    _determine_verdict,
    build_evaluation_report,
    compute_omi_comparison,
)


def make_property(
    prezzo: float | None = 280000,
    mq: float | None = 85,
    citta: str | None = "Milano",
    zona: str | None = "Navigli",
    classe_energetica: str | None = "C",
    locali: int | None = 3,
) -> PropertyData:
    return PropertyData(
        url="https://www.immobiliare.it/annunci/123/",
        portal="immobiliare",
        prezzo=prezzo,
        mq=mq,
        citta=citta,
        zona=zona,
        classe_energetica=classe_energetica,
        locali=locali,
    )


# ---------------------------------------------------------------------------
# Test: _compute_investment_score
# ---------------------------------------------------------------------------


def test_score_underpriced_good_energy():
    """Immobile sottostimato con buona classe energetica → score alto."""
    score = _compute_investment_score(
        scostamento=-15.0, classe_energetica="A2", locali=3
    )
    assert score > 60, f"Score atteso > 60, ottenuto {score}"


def test_score_overpriced():
    """Immobile soprastimato → score basso."""
    score = _compute_investment_score(
        scostamento=20.0, classe_energetica="G", locali=1
    )
    assert score < 40, f"Score atteso < 40, ottenuto {score}"


def test_score_neutral():
    """Nessuno scostamento e classe media → score neutro ~50."""
    score = _compute_investment_score(
        scostamento=0.0, classe_energetica="C", locali=3
    )
    assert 45 <= score <= 60, f"Score atteso 45-60, ottenuto {score}"


def test_score_clamped():
    """Il punteggio deve essere sempre tra 0 e 100."""
    s1 = _compute_investment_score(scostamento=-200.0, classe_energetica="A4", locali=4)
    s2 = _compute_investment_score(scostamento=200.0, classe_energetica="G", locali=1)
    assert 0 <= s1 <= 100
    assert 0 <= s2 <= 100


def test_score_no_data():
    """Senza dati opzionali il calcolo non deve sollevare eccezioni."""
    score = _compute_investment_score(scostamento=None, classe_energetica=None, locali=None)
    assert 0 <= score <= 100


# ---------------------------------------------------------------------------
# Test: _determine_verdict
# ---------------------------------------------------------------------------


def test_verdict_affare():
    verdict, desc = _determine_verdict(-10.0, 75.0)
    assert verdict == "AFFARE"
    assert "10.0" in desc


def test_verdict_soprastimato():
    verdict, desc = _determine_verdict(15.0, 25.0)
    assert verdict == "SOPRASTIMATO"


def test_verdict_mercato():
    verdict, desc = _determine_verdict(3.0, 50.0)
    assert verdict == "MERCATO"


def test_verdict_no_scostamento():
    verdict, desc = _determine_verdict(None, 50.0)
    assert verdict == "MERCATO"
    assert "insufficienti" in desc.lower()


# ---------------------------------------------------------------------------
# Test: compute_omi_comparison (con dataset reale)
# ---------------------------------------------------------------------------


def test_omi_comparison_milano():
    """Test con dataset OMI reale per Milano."""
    prop = make_property(prezzo=280000, mq=85, citta="Milano", zona="Navigli")
    # prezzo_mq = 280000/85 ≈ 3294 €/mq

    result = compute_omi_comparison(prop)

    assert result.citta_omi == "Milano"
    assert result.prezzo_min_omi is not None
    assert result.prezzo_max_omi is not None
    assert result.prezzo_medio_omi is not None
    assert result.scostamento_percentuale is not None


def test_omi_comparison_missing_city():
    """Città non nel dataset → risultato senza errori."""
    prop = make_property(citta="CittàInesistente123")
    result = compute_omi_comparison(prop)
    assert result.scostamento_percentuale is None


def test_omi_comparison_missing_price():
    """Senza prezzo/mq → impossibile calcolare lo scostamento."""
    prop = make_property(prezzo=None, mq=None)
    result = compute_omi_comparison(prop)
    assert result.scostamento_percentuale is None


def test_omi_comparison_fuzzy_city():
    """Il fuzzy matching deve trovare 'ROMA' anche scritto in modo non standard."""
    prop = make_property(citta="roma", prezzo=400000, mq=80)
    result = compute_omi_comparison(prop)
    assert result.citta_omi == "Roma"


# ---------------------------------------------------------------------------
# Test: build_evaluation_report
# ---------------------------------------------------------------------------


def test_build_report_complete():
    from app.models.property import OmiComparison

    prop = make_property()
    omi = OmiComparison(
        zona_omi="B2 - Semicentro Sud (Navigli)",
        citta_omi="Milano",
        prezzo_min_omi=3000,
        prezzo_max_omi=4800,
        prezzo_medio_omi=3900,
        scostamento_percentuale=-15.6,
        is_underpriced=True,
        semestre_omi="2023-II",
    )

    report = build_evaluation_report(prop, omi, processing_time_ms=3500)

    assert isinstance(report, EvaluationReport)
    assert report.verdict == "AFFARE"
    assert report.investment_score > 60
    assert report.processing_time_ms == 3500
    assert report.omi_comparison.citta_omi == "Milano"
