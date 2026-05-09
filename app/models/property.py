"""
Modelli Pydantic per i dati dell'immobile e il report di valutazione.
"""
from __future__ import annotations
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field, computed_field


class PropertyData(BaseModel):
    """Dati strutturati estratti dall'annuncio immobiliare tramite AI."""

    url: str = Field(..., description="URL originale dell'annuncio")
    portal: str = Field(..., description="Portale di provenienza (immobiliare/idealista/altro)")

    # --- Dati economici ---
    prezzo: Optional[float] = Field(None, description="Prezzo totale dell'immobile in €")
    mq: Optional[float] = Field(None, description="Superficie commerciale in m²")

    # --- Localizzazione ---
    indirizzo: Optional[str] = Field(None, description="Indirizzo completo o parziale")
    citta: Optional[str] = Field(None, description="Città dell'immobile")
    zona: Optional[str] = Field(None, description="Zona/quartiere/CAP")
    regione: Optional[str] = Field(None, description="Regione dell'immobile")

    # --- Caratteristiche ---
    tipologia: Optional[str] = Field(None, description="Tipologia (appartamento, villa, ecc.)")
    locali: Optional[int] = Field(None, description="Numero di locali/vani")
    camere: Optional[int] = Field(None, description="Numero di camere da letto")
    bagni: Optional[int] = Field(None, description="Numero di bagni")
    piano: Optional[str] = Field(None, description="Piano dell'immobile (es. '3° di 5')")
    ascensore: Optional[bool] = Field(None, description="Presenza ascensore")
    garage: Optional[bool] = Field(None, description="Presenza garage/posto auto")
    giardino: Optional[bool] = Field(None, description="Presenza giardino/terrazzo")
    anno_costruzione: Optional[int] = Field(None, description="Anno di costruzione o ristrutturazione")

    # --- Energia ---
    classe_energetica: Optional[str] = Field(
        None,
        description="Classe energetica (A4, A3, A2, A1, B, C, D, E, F, G)",
    )

    # --- Testo grezzo ---
    descrizione_raw: Optional[str] = Field(None, description="Testo originale dell'annuncio (primi 2000 caratteri)")

    @computed_field
    @property
    def prezzo_mq(self) -> Optional[float]:
        """Calcola il prezzo per metro quadro."""
        if self.prezzo and self.mq and self.mq > 0:
            return round(self.prezzo / self.mq, 2)
        return None


class EvaluationRequest(BaseModel):
    """Corpo della richiesta all'endpoint /evaluate."""
    url: str = Field(..., description="URL dell'annuncio immobiliare da valutare")
    provider: Literal["openai", "moonshot", "nvidia"] = Field("openai", description="Provider AI da utilizzare")
    api_key: Optional[str] = Field(None, description="Chiave API personalizzata (sovrascrive .env)")
    model: Optional[str] = Field(None, description="Modello AI da utilizzare")
    base_url: Optional[str] = Field(None, description="Base URL personalizzato per l'API (opzionale)")
    use_vision: bool = Field(True, description="Se True, usa l'AI Vision quando il testo è insufficiente")
    use_sentiment_analysis: bool = Field(True, description="Se True, esegue analisi qualitativa AI con punti di forza/deboli")
    headless: Optional[bool] = Field(None, description="Se False, mostra il browser visibile (utile per siti con anti-bot)")
    use_anti_bot: bool = Field(False, description="Se True, usa ScrapingBee proxy per bypassare anti-bot")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"url": "https://www.immobiliare.it/annunci/123456789/"},
                {"url": "https://www.idealista.it/immobile/12345678/", "provider": "moonshot"},
            ]
        }
    }


class ManualEvaluationRequest(BaseModel):
    """Richiesta per valutazione manuale senza scraping."""
    url: Optional[str] = Field(None, description="URL opzionale dell'annuncio")
    prezzo: float = Field(..., description="Prezzo totale dell'immobile in €")
    mq: float = Field(..., description="Superficie commerciale in m²")
    citta: str = Field(..., description="Città dell'immobile")
    zona: Optional[str] = Field(None, description="Zona/quartiere/CAP")
    locali: Optional[int] = Field(None, description="Numero di locali/vani")
    classe_energetica: Optional[str] = Field(None, description="Classe energetica (A4-G)")
    tipologia: Optional[str] = Field(None, description="Tipologia (appartamento, villa, ecc.)")
    camere: Optional[int] = Field(None, description="Numero di camere da letto")
    bagni: Optional[int] = Field(None, description="Numero di bagni")
    piano: Optional[str] = Field(None, description="Piano dell'immobile")
    anno_costruzione: Optional[int] = Field(None, description="Anno di costruzione o ristrutturazione")
    indirizzo: Optional[str] = Field(None, description="Indirizzo completo o parziale")
    regione: Optional[str] = Field(None, description="Regione dell'immobile")


class OmiComparison(BaseModel):
    """Risultato del confronto con i valori OMI dell'Agenzia delle Entrate."""

    zona_omi: Optional[str] = Field(None, description="Zona catastale OMI individuata")
    citta_omi: Optional[str] = Field(None, description="Città di riferimento nel dataset OMI")
    prezzo_min_omi: Optional[float] = Field(None, description="Prezzo minimo OMI (€/m²)")
    prezzo_max_omi: Optional[float] = Field(None, description="Prezzo massimo OMI (€/m²)")
    prezzo_medio_omi: Optional[float] = Field(None, description="Prezzo medio OMI calcolato (€/m²)")
    scostamento_percentuale: Optional[float] = Field(
        None,
        description="Scostamento % rispetto alla media OMI. Negativo = sottostimato (affare).",
    )
    is_underpriced: bool = Field(False, description="True se il prezzo è inferiore alla media OMI")
    semestre_omi: Optional[str] = Field(None, description="Semestre di riferimento del dato OMI")
    fonte: str = Field("Agenzia delle Entrate - Osservatorio Mercato Immobiliare", description="Fonte del dato OMI")
    note: Optional[str] = Field(None, description="Note aggiuntive sul confronto OMI (es. uso di comune proxy)")


class SentimentItem(BaseModel):
    """Singolo punto di forza o debolezza con impatto sul prezzo."""

    description: str = Field(..., description="Descrizione qualitativa del punto")
    price_impact_percent: float = Field(
        ...,
        description="Impatto percentuale sul prezzo (positivo = aumenta, negativo = diminuisce)",
    )


class SentimentAnalysis(BaseModel):
    """Analisi qualitativa AI di punti di forza e deboli dell'immobile."""

    strengths: list[SentimentItem] = Field(default_factory=list, description="Max 5 punti di forza")
    weaknesses: list[SentimentItem] = Field(default_factory=list, description="Max 5 punti deboli")


class AdjustedPriceComparison(BaseModel):
    """Confronto prezzo basato su stima OMI + aggiustamenti qualitativi."""

    prezzo_base_omi: Optional[float] = Field(None, description="Prezzo stimato da OMI (prezzo_medio_omi × mq)")
    totale_aggiustamento_percentuale: Optional[float] = Field(
        None, description="Somma algebrica degli impatti qualitativi (%)")
    prezzo_corretto: Optional[float] = Field(None, description="Prezzo base OMI corretto con aggiustamenti")
    scostamento_percentuale: Optional[float] = Field(
        None,
        description="Scostamento % del prezzo reale vs prezzo_corretto. Negativo = sottostimato.",
    )
    is_underpriced: bool = Field(False, description="True se il prezzo reale è inferiore al prezzo_corretto")
    verdict: Literal["AFFARE", "MERCATO", "SOPRASTIMATO"] = Field(
        "MERCATO", description="Verdetto basato sullo scostamento corretto"
    )
    verdict_description: str = Field("", description="Spiegazione del verdetto corretto")


class EvaluationReport(BaseModel):
    """Report completo di valutazione immobiliare."""

    property_data: PropertyData = Field(..., description="Dati strutturati dell'immobile")
    omi_comparison: OmiComparison = Field(..., description="Confronto con valori OMI")
    sentiment_analysis: Optional[SentimentAnalysis] = Field(
        None, description="Analisi qualitativa AI di punti di forza/deboli"
    )
    adjusted_comparison: Optional[AdjustedPriceComparison] = Field(
        None, description="Confronto prezzo con aggiustamenti qualitativi"
    )

    investment_score: float = Field(
        ...,
        ge=0,
        le=100,
        description="Punteggio di investimento 0-100 (100 = massima convenienza)",
    )
    verdict: Literal["AFFARE", "MERCATO", "SOPRASTIMATO"] = Field(
        ..., description="Verdetto sintetico sulla convenienza dell'immobile"
    )
    verdict_description: str = Field(..., description="Spiegazione dettagliata del verdetto")

    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Timestamp dell'analisi (UTC)")
    processing_time_ms: Optional[int] = Field(None, description="Tempo di elaborazione in millisecondi")
    screenshot_base64: Optional[str] = Field(None, description="Screenshot della pagina quando il testo è insufficiente")


class RecalculateRequest(BaseModel):
    """Corpo della richiesta per ricalcolare la valutazione con sentiment modificato."""

    property_data: PropertyData = Field(..., description="Dati dell'immobile")
    omi_comparison: OmiComparison = Field(..., description="Dati OMI già calcolati")
    sentiment_analysis: SentimentAnalysis = Field(..., description="Analisi qualitativa modificata dall'utente")


class RecalculateResponse(BaseModel):
    """Risposta del ricalcolo con nuova stima corretta."""

    adjusted_comparison: AdjustedPriceComparison = Field(..., description="Nuovo confronto prezzo corretto")
    investment_score: float = Field(..., ge=0, le=100, description="Investment Score aggiornato")
    verdict: Literal["AFFARE", "MERCATO", "SOPRASTIMATO"] = Field(..., description="Verdetto aggiornato")
    verdict_description: str = Field(..., description="Descrizione aggiornata del verdetto")


class EstimateSentimentRequest(BaseModel):
    """Richiesta per stimare l'impatto di un nuovo bonus/malus."""

    text: str = Field(..., min_length=3, description="Descrizione testuale del bonus/malus")
    property_data: Optional[PropertyData] = Field(None, description="Dati dell'immobile per contesto (opzionale)")
    provider: Literal["openai", "moonshot", "nvidia"] = Field("openai", description="Provider AI")
    api_key: Optional[str] = Field(None, description="Chiave API personalizzata")
    model: Optional[str] = Field(None, description="Modello AI")
    base_url: Optional[str] = Field(None, description="Base URL personalizzato")


class EstimateSentimentResponse(BaseModel):
    """Risposta con il SentimentItem stimato dall'AI."""

    item: SentimentItem = Field(..., description="Item stimato con descrizione e impatto percentuale")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "property_data": {
                        "url": "https://www.immobiliare.it/annunci/123/",
                        "portal": "immobiliare",
                        "prezzo": 280000,
                        "mq": 85,
                        "citta": "Milano",
                        "zona": "Navigli",
                        "tipologia": "Appartamento",
                        "locali": 3,
                        "classe_energetica": "C",
                        "prezzo_mq": 3294.12,
                    },
                    "omi_comparison": {
                        "zona_omi": "D1",
                        "citta_omi": "Milano",
                        "prezzo_min_omi": 2800.0,
                        "prezzo_max_omi": 4200.0,
                        "prezzo_medio_omi": 3500.0,
                        "scostamento_percentuale": -5.88,
                        "is_underpriced": True,
                        "semestre_omi": "2023-II",
                        "fonte": "Agenzia delle Entrate - Osservatorio Mercato Immobiliare",
                    },
                    "investment_score": 72.5,
                    "verdict": "AFFARE",
                    "verdict_description": "L'immobile è prezzato sotto la media OMI del 5.88%.",
                    "timestamp": "2024-01-15T10:30:00Z",
                    "processing_time_ms": 4523,
                }
            ]
        }
    }
