"""
Entry point principale dell'applicazione FastAPI.
Avvia il server con: uvicorn app.main:app --reload
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.endpoints.admin import router as admin_router
from app.api.v1.endpoints.evaluate import router as evaluate_router
from app.core.config import get_settings
from app.core.logging import logger

settings = get_settings()


# ---------------------------------------------------------------------------
# Static files (frontend SPA)
# ---------------------------------------------------------------------------

STATIC_DIR = Path(__file__).resolve().parent.parent / "frontend"


# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Gestisce il ciclo di vita dell'applicazione.
    All'avvio installa/verifica il browser Playwright.
    """
    logger.info("🚀 Avvio %s v%s [%s]", settings.app_name, settings.app_version, settings.app_env)

    # Verifica che il browser Playwright sia installato
    import sys
    try:
        # La verifica tramite subprocess non funziona su Windows con uvicorn --reload.
        # Controlliamo solo l'importazione del modulo.
        from playwright._impl._driver import compute_driver_executable
        driver = compute_driver_executable()
        if driver[0].exists():
            logger.info("\u2705 Browser Playwright (Chromium) disponibile")
        else:
            logger.warning("\u26a0\ufe0f  Esegui: python -m playwright install chromium")
    except Exception as exc:
        logger.warning("\u26a0\ufe0f  Playwright non verificabile all'avvio: %s", exc)

    yield

    logger.info("🛑 Applicazione in chiusura...")


# ---------------------------------------------------------------------------
# Istanza FastAPI
# ---------------------------------------------------------------------------


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "**AI Property Analyzer & Valuation** — Strumento intelligente per la valutazione "
        "in tempo reale della convenienza degli investimenti immobiliari.\n\n"
        "## Come funziona\n"
        "1. Invia l'URL di un annuncio su `Immobiliare.it` o `Idealista.it`\n"
        "2. Il sistema esegue lo scraping, estrae i dati con GPT-4o\n"
        "3. Confronta il prezzo con le medie OMI dell'Agenzia delle Entrate\n"
        "4. Restituisce un report completo con **Investment Score** e verdetto\n\n"
        "## Verdetti possibili\n"
        "| Verdetto | Significato |\n"
        "|----------|-------------|\n"
        "| 🟢 **AFFARE** | Prezzo > 5% sotto la media OMI |\n"
        "| 🟡 **MERCATO** | Prezzo allineato alle medie OMI |\n"
        "| 🔴 **SOPRASTIMATO** | Prezzo > 8% sopra la media OMI |"
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Da restringere in produzione
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

app.include_router(
    evaluate_router,
    prefix="/api/v1",
    tags=["Valutazione"],
)

app.include_router(
    admin_router,
    prefix="/api/v1",
    tags=["Amministrazione"],
)


# ---------------------------------------------------------------------------
# Endpoint di sistema
# ---------------------------------------------------------------------------


@app.get(
    "/health",
    summary="Health Check",
    tags=["Sistema"],
    response_description="Stato dell'applicazione",
)
async def health_check() -> JSONResponse:
    """Verifica che il servizio sia attivo e risponda correttamente."""
    return JSONResponse(
        content={
            "status": "ok",
            "service": settings.app_name,
            "version": settings.app_version,
            "environment": settings.app_env,
        }
    )


# ---------------------------------------------------------------------------
# Static files + SPA fallback (html=True serve index.html per route non trovate)
# DEVE essere l'ultimo per non sovrascrivere le API routes
# ---------------------------------------------------------------------------

if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="frontend")
