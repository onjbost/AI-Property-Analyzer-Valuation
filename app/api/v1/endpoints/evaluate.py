"""
Endpoint FastAPI per la valutazione di annunci immobiliari.
POST /api/v1/evaluate
"""
from __future__ import annotations

import time
from typing import Annotated

import openai
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse

from app.core.logging import logger
from app.models.property import EvaluationReport, EvaluationRequest, ManualEvaluationRequest, PropertyData, OmiComparison
from app.services.adjusted_price import compute_adjusted_comparison
from app.services.extractor import PropertyExtractor
from app.services.omi_calculator import build_evaluation_report, compute_omi_comparison
from app.services.scraper import scrape_property
from app.services.sentiment_analyzer import PropertySentimentAnalyzer

router = APIRouter()


@router.post(
    "/evaluate",
    response_model=EvaluationReport,
    status_code=status.HTTP_200_OK,
    summary="Valuta un annuncio immobiliare",
    description=(
        "Riceve l'URL di un annuncio immobiliare (Immobiliare.it o Idealista.it), "
        "esegue lo scraping, estrae i dati con AI (OpenAI o Moonshot) e confronta il prezzo "
        "con i valori OMI dell'Agenzia delle Entrate."
    ),
    response_description="Report completo di valutazione con Investment Score e verdetto",
    tags=["Valutazione"],
)
async def evaluate_property(request: EvaluationRequest) -> EvaluationReport:
    """
    Pipeline completa di valutazione immobiliare:

    1. **Scraping** — Playwright estrae il contenuto dalla pagina dell'annuncio
    2. **Estrazione AI** — GPT-4o trasforma il testo in dati strutturati
    3. **Confronto OMI** — Calcola lo scostamento rispetto alle medie di mercato
    4. **Report** — Assembla il report finale con Investment Score e verdetto
    """
    url = str(request.url)
    logger.info("═══ NUOVA VALUTAZIONE | url=%s", url)
    logger.info(
        "Parametri richiesta | provider=%s | api_key=%s | model=%s | headless=%s | anti_bot=%s",
        request.provider,
        "presente" if request.api_key else "mancante",
        request.model,
        request.headless,
        request.use_anti_bot,
    )
    start_time = time.monotonic()

    # ------------------------------------------------------------------ #
    # STEP 1 — Scraping
    # ------------------------------------------------------------------ #
    logger.info("[1/3] Avvio scraping...")
    scraper_result = await scrape_property(url, headless=request.headless, use_anti_bot=request.use_anti_bot)

    if not scraper_result.success:
        logger.error("Scraping fallito: %s", scraper_result.error)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": "scraping_failed",
                "message": "Impossibile recuperare i dati dalla pagina dell'annuncio.",
                "detail": scraper_result.error,
                "url": url,
            },
        )

    has_content = bool(scraper_result.text_content) or bool(scraper_result.screenshot_base64)
    if not has_content:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "empty_content",
                "message": "La pagina non contiene contenuto estraibile. Potrebbe essere protetta da bot.",
                "url": url,
            },
        )

    # ------------------------------------------------------------------ #
    # STEP 2 — Estrazione AI
    # ------------------------------------------------------------------ #
    property_data = None
    use_vision_fallback = (
        request.use_vision
        and not scraper_result.text_content
        and scraper_result.screenshot_base64
    )

    if scraper_result.text_content or use_vision_fallback:
        logger.info("[2/4] Estrazione dati con AI...")
        try:
            extractor = PropertyExtractor(
                provider=request.provider,
                api_key=request.api_key,
                model=request.model,
                base_url=request.base_url,
            )
            property_data = await extractor.extract(scraper_result)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "missing_api_key",
                    "message": str(exc),
                },
            )
        except openai.AuthenticationError as exc:
            logger.error("AuthenticationError AI | provider=%s | detail=%s", request.provider, exc)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": "invalid_api_key",
                    "message": "API key non valida per il provider selezionato. Verifica le Impostazioni.",
                    "detail": str(exc),
                },
            )
        except Exception as exc:
            if use_vision_fallback:
                logger.warning(
                    "Vision fallita, restituisco report parziale con screenshot: %s", exc
                )
            else:
                logger.exception("Errore durante l'estrazione AI: %s", exc)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail={
                        "error": "extraction_failed",
                        "message": "Errore durante l'analisi AI del contenuto.",
                        "detail": str(exc),
                    },
                )

    # ------------------------------------------------------------------ #
    # STEP 3 — Analisi qualitativa AI (sentiment)
    # ------------------------------------------------------------------ #
    sentiment_analysis = None
    if property_data is not None and request.use_sentiment_analysis:
        logger.info("[3/4] Analisi qualitativa AI...")
        try:
            analyzer = PropertySentimentAnalyzer(
                provider=request.provider,
                api_key=request.api_key,
                model=request.model,
                base_url=request.base_url,
            )
            sentiment_analysis = await analyzer.analyze(property_data, scraper_result)
        except Exception as exc:
            logger.warning("Analisi qualitativa non riuscita, prosegue senza: %s", exc)
            sentiment_analysis = None

    # ------------------------------------------------------------------ #
    # STEP 4 — Confronto OMI e generazione report
    # ------------------------------------------------------------------ #
    logger.info("[4/4] Confronto OMI, prezzo corretto e calcolo Investment Score...")

    if property_data is None:
        # Report parziale: screenshot disponibile ma nessun dato estratto
        property_data = PropertyData(url=url, portal=scraper_result.portal)
        omi_comparison = OmiComparison()
        report = EvaluationReport(
            property_data=property_data,
            omi_comparison=omi_comparison,
            investment_score=0.0,
            verdict="MERCATO",
            verdict_description=(
                "Impossibile estrarre dati strutturati dalla pagina. "
                "Lo screenshot dell'annuncio è disponibile qui sotto. "
                "Il sito potrebbe richiedere una verifica anti-bot o JavaScript aggiuntivo."
            ),
            processing_time_ms=int((time.monotonic() - start_time) * 1000),
            screenshot_base64=scraper_result.screenshot_base64,
        )
    else:
        omi_comparison = compute_omi_comparison(property_data)
        adjusted_comparison = compute_adjusted_comparison(
            property_data, omi_comparison, sentiment_analysis
        )
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        report = build_evaluation_report(property_data, omi_comparison, processing_time_ms=elapsed_ms)
        report.sentiment_analysis = sentiment_analysis
        report.adjusted_comparison = adjusted_comparison
        if scraper_result.screenshot_base64:
            report.screenshot_base64 = scraper_result.screenshot_base64

    logger.info(
        "═══ VALUTAZIONE COMPLETATA | verdict=%s | score=%.1f | tempo=%dms",
        report.verdict,
        report.investment_score,
        report.processing_time_ms,
    )

    return report


@router.post(
    "/evaluate-manual",
    response_model=EvaluationReport,
    status_code=status.HTTP_200_OK,
    summary="Valuta un immobile da dati manuali",
    description=(
        "Riceve i dati di un immobile inseriti manualmente, calcola il prezzo per m² "
        "e confronta con le medie OMI. Nessuno scraping o AI coinvolti."
    ),
    response_description="Report di valutazione con Investment Score e verdetto",
    tags=["Valutazione"],
)
async def evaluate_manual(request: ManualEvaluationRequest) -> EvaluationReport:
    """
    Valutazione immobiliare da dati inseriti manualmente.
    """
    logger.info("═══ VALUTAZIONE MANUALE | città=%s | prezzo=%s | mq=%s", request.citta, request.prezzo, request.mq)
    start_time = time.monotonic()

    property_data = PropertyData(
        url=request.url or "manuale",
        portal="manuale",
        prezzo=request.prezzo,
        mq=request.mq,
        citta=request.citta,
        zona=request.zona,
        locali=request.locali,
        classe_energetica=request.classe_energetica,
        tipologia=request.tipologia,
        camere=request.camere,
        bagni=request.bagni,
        piano=request.piano,
        anno_costruzione=request.anno_costruzione,
        indirizzo=request.indirizzo,
        regione=request.regione,
    )

    omi_comparison = compute_omi_comparison(property_data)
    elapsed_ms = int((time.monotonic() - start_time) * 1000)
    report = build_evaluation_report(property_data, omi_comparison, processing_time_ms=elapsed_ms)

    logger.info(
        "═══ VALUTAZIONE MANUALE COMPLETATA | verdict=%s | score=%.1f | tempo=%dms",
        report.verdict,
        report.investment_score,
        elapsed_ms,
    )

    return report
