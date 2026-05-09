"""
Modulo di calcolo del prezzo corretto basato su stima OMI + aggiustamenti qualitativi.
"""
from __future__ import annotations

from typing import Optional

from app.core.logging import logger
from app.models.property import (
    AdjustedPriceComparison,
    OmiComparison,
    PropertyData,
    SentimentAnalysis,
)

# Soglie per il verdetto corretto (leggermente più morbide dell'OMI)
ADJ_UNDERPRICED_THRESHOLD = -5.0
ADJ_OVERPRICED_THRESHOLD = 8.0


def compute_adjusted_comparison(
    property_data: PropertyData,
    omi_comparison: OmiComparison,
    sentiment_analysis: Optional[SentimentAnalysis],
) -> Optional[AdjustedPriceComparison]:
    """
    Calcola il prezzo corretto partendo dalla stima OMI e applicando
    gli aggiustamenti qualitativi (punti di forza/deboli).

    Formula:
    - prezzo_base_omi = prezzo_medio_omi × mq
    - totale_aggiustamento = somma impatti qualitativi (%)
    - prezzo_corretto = prezzo_base_omi × (1 + totale/100)
    - scostamento = ((prezzo_reale - prezzo_corretto) / prezzo_corretto) × 100
    """
    # Validazione dati minimi
    if (
        not sentiment_analysis
        or omi_comparison.prezzo_medio_omi is None
        or property_data.mq is None
        or property_data.mq <= 0
        or property_data.prezzo is None
    ):
        logger.debug("Dati insufficienti per calcolo prezzo corretto")
        return None

    # 1. Prezzo base da OMI
    prezzo_base = round(omi_comparison.prezzo_medio_omi * property_data.mq, 2)

    # 2. Somma aggiustamenti qualitativi
    total_adjustment = 0.0
    if sentiment_analysis.strengths:
        total_adjustment += sum(s.price_impact_percent for s in sentiment_analysis.strengths)
    if sentiment_analysis.weaknesses:
        total_adjustment += sum(w.price_impact_percent for w in sentiment_analysis.weaknesses)

    total_adjustment = round(total_adjustment, 2)

    # 3. Prezzo corretto
    prezzo_corretto = round(prezzo_base * (1 + total_adjustment / 100), 2)

    # Evita divisione per zero o valori negativi assurdi
    if prezzo_corretto <= 0:
        logger.warning("Prezzo corretto non valido: %.2f", prezzo_corretto)
        return None

    # 4. Scostamento vs prezzo reale
    scostamento = round(
        ((property_data.prezzo - prezzo_corretto) / prezzo_corretto) * 100, 2
    )
    is_underpriced = scostamento < 0

    # 5. Verdetto
    if scostamento <= ADJ_UNDERPRICED_THRESHOLD:
        verdict = "AFFARE"
        verdict_desc = (
            f"Considerando gli aggiustamenti qualitativi ({total_adjustment:+.1f}%), "
            f"il prezzo è {abs(scostamento):.1f}% sotto il valore corretto stimato."
        )
    elif scostamento >= ADJ_OVERPRICED_THRESHOLD:
        verdict = "SOPRASTIMATO"
        verdict_desc = (
            f"Considerando gli aggiustamenti qualitativi ({total_adjustment:+.1f}%), "
            f"il prezzo è {scostamento:.1f}% sopra il valore corretto stimato."
        )
    else:
        verdict = "MERCATO"
        verdict_desc = (
            f"Considerando gli aggiustamenti qualitativi ({total_adjustment:+.1f}%), "
            f"il prezzo è allineato al valore corretto stimato (scostamento: {scostamento:+.1f}%)."
        )

    logger.info(
        "Prezzo corretto | base=%.0f | aggiustamento=%+.1f%% | corretto=%.0f | scostamento=%+.1f%% | %s",
        prezzo_base,
        total_adjustment,
        prezzo_corretto,
        scostamento,
        verdict,
    )

    return AdjustedPriceComparison(
        prezzo_base_omi=prezzo_base,
        totale_aggiustamento_percentuale=total_adjustment,
        prezzo_corretto=prezzo_corretto,
        scostamento_percentuale=scostamento,
        is_underpriced=is_underpriced,
        verdict=verdict,
        verdict_description=verdict_desc,
    )
