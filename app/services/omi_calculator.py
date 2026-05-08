"""
Modulo di calcolo e confronto con i valori OMI (Osservatorio Mercato Immobiliare).
Determina la convenienza dell'immobile rispetto alle medie dell'Agenzia delle Entrate.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Optional

import pandas as pd
from thefuzz import process as fuzz_process

from app.core.config import get_settings
from app.core.logging import logger
from app.models.property import EvaluationReport, OmiComparison, PropertyData

settings = get_settings()

# ---------------------------------------------------------------------------
# Pesi per il calcolo dell'Investment Score
# ---------------------------------------------------------------------------

# Moltiplicatori per classe energetica (migliore = punteggio più alto)
ENERGY_SCORE: dict[str, float] = {
    "A4": 1.20, "A3": 1.15, "A2": 1.10, "A1": 1.08,
    "B": 1.04, "C": 1.00, "D": 0.95, "E": 0.88,
    "F": 0.80, "G": 0.72,
}

# Bonus/malus per numero di locali
LOCALI_BONUS: dict[int, float] = {1: -2.0, 2: 0.0, 3: 3.0, 4: 4.0, 5: 3.0}
LOCALI_DEFAULT_BONUS: float = 2.5  # per 6+ locali

# Soglie per il verdetto
UNDERPRICED_THRESHOLD = -5.0   # scostamento < -5% -> AFFARE
OVERPRICED_THRESHOLD = 8.0     # scostamento > +8% -> SOPRASTIMATO

# ---------------------------------------------------------------------------
# Caricamento dataset OMI
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _load_omi_dataframe() -> pd.DataFrame:
    """Carica il CSV OMI in memoria (caching singleton)."""
    csv_path = Path(settings.omi_csv_path)
    if not csv_path.exists():
        logger.warning("File OMI non trovato: %s", csv_path)
        return pd.DataFrame()

    df = pd.read_csv(csv_path)
    df.columns = [c.strip().lower() for c in df.columns]
    df["citta"] = df["citta"].str.strip().str.title()
    df["zona"] = df["zona"].str.strip()
    logger.info("Dataset OMI caricato: %d righe da %s", len(df), csv_path)
    return df


# ---------------------------------------------------------------------------
# Logica di matching
# ---------------------------------------------------------------------------


def _find_best_city_match(citta: str, df: pd.DataFrame) -> Optional[str]:
    """Trova la città più simile nel dataset OMI tramite fuzzy matching."""
    available_cities = df["citta"].unique().tolist()
    if not available_cities:
        return None

    # Soglia alta per evitare match casuali (es. Trabia -> Catania)
    result = fuzz_process.extractOne(citta.title(), available_cities, score_cutoff=85)
    if result:
        match, score = result[0], result[1]
        logger.info("City fuzzy match: '%s' -> '%s' (score=%d)", citta, match, score)
        return match
    logger.warning("Città '%s' non trovata nel dataset OMI (nessun match affidabile)", citta)
    return None


def _find_best_zone_match(zona: Optional[str], city_df: pd.DataFrame) -> Optional[pd.Series]:
    """Trova la zona OMI più vicina nella città, preferendo il centro storico come fallback."""
    available_zones = city_df["zona"].unique().tolist()

    if zona:
        result = fuzz_process.extractOne(zona, available_zones, score_cutoff=40)
        if result:
            matched_zone = result[0]
            logger.debug("Zone fuzzy match: '%s' -> '%s'", zona, matched_zone)
            subset = city_df[city_df["zona"] == matched_zone]
            if not subset.empty:
                return subset.iloc[0]

    # Fallback: prima zona disponibile (solitamente il centro)
    return city_df.iloc[0] if not city_df.empty else None


# ---------------------------------------------------------------------------
# Fallback geografico
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _load_comuni_coords() -> dict[str, tuple[float, float]]:
    """Carica le coordinate dei comuni italiani dal JSON di cache."""
    coords_path = Path("app/data/comuni_coords.json")
    if not coords_path.exists():
        logger.warning("File coordinate comuni non trovato: %s", coords_path)
        return {}
    data = json.loads(coords_path.read_text(encoding="utf-8"))
    return {k.title(): (v[0], v[1]) for k, v in data.items()}


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distanza tra due punti geografici in km (formula di Haversine)."""
    R = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _find_nearest_city(target_city: str, df: pd.DataFrame) -> Optional[tuple[str, float]]:
    """
    Trova il comune nel dataset OMI più vicino geograficamente a target_city.
    Restituisce (nome_comune, distanza_km) o None se le coordinate non sono disponibili.
    """
    coords = _load_comuni_coords()
    target = coords.get(target_city.title())
    if not target:
        logger.warning("Coordinate non disponibili per '%s'", target_city)
        return None

    available_cities = df["citta"].unique().tolist()
    best_city = None
    best_dist = float("inf")

    for city in available_cities:
        city_coord = coords.get(city)
        if not city_coord:
            continue
        dist = _haversine_km(target[0], target[1], city_coord[0], city_coord[1])
        if dist < best_dist:
            best_dist = dist
            best_city = city

    if best_city:
        logger.info(
            "Fallback geografico: '%s' -> '%s' (distanza %.1f km)",
            target_city,
            best_city,
            best_dist,
        )
        return best_city, best_dist
    return None


# ---------------------------------------------------------------------------
# Calcolo Investment Score
# ---------------------------------------------------------------------------


def _compute_investment_score(
    scostamento: Optional[float],
    classe_energetica: Optional[str],
    locali: Optional[int],
) -> float:
    """
    Calcola un punteggio di investimento da 0 a 100.

    Formula:
    - Base: 50 punti (posizione neutra)
    - Scostamento OMI: ±30 punti (inversamente proporzionale allo scostamento)
    - Classe energetica: ±10 punti
    - Numero locali: ±5 punti
    """
    score = 50.0

    # Componente scostamento (peso: 60% del punteggio totale)
    if scostamento is not None:
        # Scostamento negativo = immobile sottostimato = punteggio più alto
        # Clamp su [-50, +50] per non sforare
        clamped = max(-50.0, min(50.0, scostamento))
        score -= clamped * 0.6  # Inversamente proporzionale

    # Componente classe energetica (peso: 20%)
    if classe_energetica:
        multiplier = ENERGY_SCORE.get(classe_energetica.upper(), 1.0)
        energy_bonus = (multiplier - 1.0) * 100  # da -28 a +20
        score += energy_bonus * 0.2

    # Componente numero locali (peso: 10%)
    if locali is not None:
        bonus = LOCALI_BONUS.get(locali, LOCALI_DEFAULT_BONUS)
        score += bonus * 0.5

    # Normalizza tra 0 e 100
    return round(max(0.0, min(100.0, score)), 1)


def _determine_verdict(
    scostamento: Optional[float], score: float
) -> tuple[str, str]:
    """Determina il verdetto e la sua descrizione testuale."""
    if scostamento is None:
        return "MERCATO", "Impossibile confrontare con OMI: dati insufficienti per determinare il valore di mercato."

    if scostamento <= UNDERPRICED_THRESHOLD:
        diff = abs(scostamento)
        return (
            "AFFARE",
            f"L'immobile è prezzato {diff:.1f}% sotto la media OMI. "
            f"Potenziale margine di acquisto interessante (score: {score}/100).",
        )
    elif scostamento >= OVERPRICED_THRESHOLD:
        diff = abs(scostamento)
        return (
            "SOPRASTIMATO",
            f"L'immobile è prezzato {diff:.1f}% sopra la media OMI. "
            f"Valuta attentamente prima di procedere (score: {score}/100).",
        )
    else:
        return (
            "MERCATO",
            f"Il prezzo è allineato alla media OMI (scostamento: {scostamento:+.1f}%). "
            f"Immobile a prezzo di mercato (score: {score}/100).",
        )


# ---------------------------------------------------------------------------
# Funzione pubblica principale
# ---------------------------------------------------------------------------


def compute_omi_comparison(property_data: PropertyData) -> OmiComparison:
    """
    Confronta i dati dell'immobile con il dataset OMI.
    Restituisce un oggetto OmiComparison con tutti i dettagli.
    """
    df = _load_omi_dataframe()

    # Impossibile confrontare senza città o prezzo/mq
    if df.empty or not property_data.citta or property_data.prezzo_mq is None:
        logger.warning(
            "Confronto OMI impossibile | città=%s | prezzo_mq=%s",
            property_data.citta,
            property_data.prezzo_mq,
        )
        return OmiComparison(
            is_underpriced=False,
            scostamento_percentuale=None,
        )

    # 1. Trova la città nel dataset
    matched_city = _find_best_city_match(property_data.citta, df)
    note = None
    if not matched_city:
        logger.warning("Città '%s' non trovata nel dataset OMI — provo fallback geografico", property_data.citta)
        nearest = _find_nearest_city(property_data.citta, df)
        if nearest:
            matched_city, dist_km = nearest
            note = (
                f"Dati OMI non disponibili per {property_data.citta.title()}. "
                f"Confronto effettuato con il comune più vicino: {matched_city} ({dist_km:.1f} km)."
            )
        else:
            logger.warning("Città '%s' non trovata nel dataset OMI", property_data.citta)
            return OmiComparison(is_underpriced=False)

    # 2. Filtra il dataset per la città
    city_df = df[df["citta"] == matched_city].copy()

    # 3. Trova la zona più vicina
    best_row = _find_best_zone_match(property_data.zona, city_df)
    if best_row is None:
        logger.warning("Nessuna zona OMI trovata per '%s'", matched_city)
        return OmiComparison(citta_omi=matched_city, is_underpriced=False)

    # 4. Estrai i valori OMI
    prezzo_min = float(best_row.get("prezzo_min_mq", 0))
    prezzo_max = float(best_row.get("prezzo_max_mq", 0))
    prezzo_medio = round((prezzo_min + prezzo_max) / 2, 2)
    semestre = str(best_row.get("semestre", "N/D"))
    zona_name = str(best_row.get("zona", ""))

    # 5. Calcola scostamento
    scostamento = None
    if prezzo_medio > 0 and property_data.prezzo_mq:
        scostamento = round(
            ((property_data.prezzo_mq - prezzo_medio) / prezzo_medio) * 100, 2
        )

    is_underpriced = scostamento is not None and scostamento < 0

    logger.info(
        "Confronto OMI | città=%s | zona=%s | prezzo_mq=%.0f | omi_medio=%.0f | scostamento=%s%%",
        matched_city,
        zona_name,
        property_data.prezzo_mq or 0,
        prezzo_medio,
        f"{scostamento:+.1f}" if scostamento is not None else "N/A",
    )

    return OmiComparison(
        zona_omi=zona_name,
        citta_omi=matched_city,
        prezzo_min_omi=prezzo_min,
        prezzo_max_omi=prezzo_max,
        prezzo_medio_omi=prezzo_medio,
        scostamento_percentuale=scostamento,
        is_underpriced=is_underpriced,
        semestre_omi=semestre,
        note=note,
    )


def build_evaluation_report(
    property_data: PropertyData,
    omi_comparison: OmiComparison,
    processing_time_ms: Optional[int] = None,
) -> EvaluationReport:
    """
    Assembla il report finale combinando PropertyData, OmiComparison,
    Investment Score e Verdetto.
    """
    score = _compute_investment_score(
        scostamento=omi_comparison.scostamento_percentuale,
        classe_energetica=property_data.classe_energetica,
        locali=property_data.locali,
    )
    verdict, verdict_description = _determine_verdict(
        omi_comparison.scostamento_percentuale, score
    )

    return EvaluationReport(
        property_data=property_data,
        omi_comparison=omi_comparison,
        investment_score=score,
        verdict=verdict,
        verdict_description=verdict_description,
        processing_time_ms=processing_time_ms,
    )
