"""
Scraper resiliente per portali immobiliari italiani.
Usa Playwright in modalità sincrona eseguita in un thread dedicato,
così da evitare conflitti con l'event loop asyncio di FastAPI/Uvicorn su Windows.

Supporta: Immobiliare.it, Idealista.it
"""
from __future__ import annotations

import asyncio
import base64
import httpx
import random
import re
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    sync_playwright,
)

from app.core.config import get_settings
from app.core.logging import logger

settings = get_settings()

# ---------------------------------------------------------------------------
# Costanti
# ---------------------------------------------------------------------------

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]

# Selettori specifici per portale (dal più specifico al più generico)
PORTAL_SELECTORS: dict[str, list[str]] = {
    "immobiliare": [
        # Descrizione espansa
        ".re-description__text",
        "[data-qa='description']",
        ".in-description__content",
        # Container principale annuncio
        "[class*='nd-mediaObject__content']",
        "[class*='in-description']",
        "[class*='re-description']",
        ".nd-mediaObject",
        "section[class*='description']",
        # Liste caratteristiche
        ".re-features__list",
        ".re-features",
        ".re-list",
        # Generici
        "article",
        "main",
    ],
    "idealista": [
        ".detail-info-title",
        ".detail-info",
        "#details",
        ".txt-bold.txt-large",
        "[class*='detail']",
        "article",
        "main",
    ],
    "default": ["main", "article", "body"],
}

# Selettori per espandere testo nascosto
READ_MORE_SELECTORS = [
    "button:has-text('Mostra tutto')",
    "button:has-text('Leggi di più')",
    "button:has-text('Mostra altro')",
    "button:has-text('Read more')",
    "[data-qa='readAll']",
    ".re-readAll",
    ".in-readAll",
    "a:has-text('Mostra tutto')",
]

# Selettori cookie banner
COOKIE_SELECTORS = [
    "button[id*='accept']",
    "button[class*='accept']",
    "button[class*='cookie']",
    "button[class*='consent']",
    "#onetrust-accept-btn-handler",
    "[aria-label*='accetta']",
    "[aria-label*='accept']",
    "button:has-text('Accetta')",
    "button:has-text('Accetto')",
    "button:has-text('Accept')",
    "button:has-text('Accetta tutto')",
    "button:has-text('Ho capito')",
    "button:has-text('Continua')",
    "button:has-text('OK')",
]

MAX_RETRIES = 3
RETRY_DELAY_BASE = 2.0  # secondi

# Pattern da bloccare (solo tracker/pubblicità, NON immagini/font)
BLOCKED_TRACKER_PATTERNS = [
    r"google-analytics",
    r"googletagmanager",
    r"facebook\.com/tr",
    r"connect\.facebook",
    r"doubleclick",
    r"adsystem",
    r"amazon-adsystem",
    r"googlesyndication",
    r"googleadservices",
    r"hotjar",
    r"segment",
    r"mixpanel",
    r"bugsnag",
    r"sentry",
    r"matomo",
    r"plausible",
]

BLOCKED_REGEX = re.compile("|".join(BLOCKED_TRACKER_PATTERNS), re.IGNORECASE)


# ---------------------------------------------------------------------------
# Dataclass risultato
# ---------------------------------------------------------------------------


@dataclass
class ScraperResult:
    """Risultato dell'operazione di scraping."""
    url: str
    portal: str
    text_content: str
    screenshot_base64: Optional[str] = None
    page_title: Optional[str] = None
    success: bool = True
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Funzioni di utilità
# ---------------------------------------------------------------------------


def detect_portal(url: str) -> str:
    """Rileva il portale immobiliare dall'URL."""
    hostname = urlparse(url).hostname or ""
    if "immobiliare.it" in hostname:
        return "immobiliare"
    if "idealista.it" in hostname or "idealista.com" in hostname:
        return "idealista"
    return "default"


def _random_delay(min_s: float = 1.0, max_s: float = 3.0) -> float:
    """Genera un ritardo casuale per simulare comportamento umano."""
    return random.uniform(min_s, max_s)


# ---------------------------------------------------------------------------
# Scraper sincrono (interno)
# ---------------------------------------------------------------------------


class _PropertyScraperSync:
    """
    Scraper sincrono basato su Playwright.
    Viene eseguito in un thread separato tramite asyncio.to_thread().
    """

    def __init__(self) -> None:
        self._playwright = None
        self._browser: Optional[Browser] = None

    def start(self, headless: Optional[bool] = None, use_anti_bot: bool = False) -> None:
        self._playwright = sync_playwright().start()
        is_headless = headless if headless is not None else settings.playwright_headless
        self._browser = self._playwright.chromium.launch(
            headless=is_headless,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-dev-shm-usage",
                "--disable-infobars",
                "--no-first-run",
                "--no-zygote",
                "--disable-setuid-sandbox",
            ],
        )
        self._use_anti_bot = use_anti_bot
        logger.info("Browser Playwright avviato (headless=%s, anti_bot=%s)", is_headless, use_anti_bot)

    def stop(self) -> None:
        try:
            if self._browser:
                self._browser.close()
                self._browser = None
        except Exception as e:
            logger.debug("Errore chiusura browser: %s", e)
        try:
            if self._playwright:
                self._playwright.stop()
                self._playwright = None
        except Exception as e:
            logger.debug("Errore chiusura playwright: %s", e)
        logger.info("Browser Playwright chiuso.")

    def scrape(self, url: str, headless: Optional[bool] = None, use_anti_bot: bool = False) -> ScraperResult:
        portal = detect_portal(url)
        logger.info("Avvio scraping | portale=%s | url=%s", portal, url)

        last_error: Optional[str] = None
        last_error: Optional[str] = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                result = self._scrape_once(url, portal, headless=headless, use_anti_bot=use_anti_bot)
                logger.info(
                    "Scraping completato | tentativo=%d | caratteri=%d",
                    attempt,
                    len(result.text_content),
                )
                return result
            except Exception as exc:
                last_error = str(exc)
                logger.warning(
                    "Tentativo %d/%d fallito: %s", attempt, MAX_RETRIES, last_error
                )
                if attempt < MAX_RETRIES:
                    delay = RETRY_DELAY_BASE * attempt + _random_delay(0.5, 1.5)
                    logger.debug("Attesa %.1fs prima del retry...", delay)
                    time.sleep(delay)

        logger.error("Scraping fallito dopo %d tentativi: %s", MAX_RETRIES, last_error)
        return ScraperResult(
            url=url,
            portal=portal,
            text_content="",
            success=False,
            error=last_error,
        )

    def _fetch_via_scrapingbee_api(self, url: str) -> Optional[str]:
        """Recupera l'HTML di una pagina tramite ScrapingBee API (render_js + premium proxy)."""
        api_url = (
            f"https://app.scrapingbee.com/api/v1/"
            f"?api_key={settings.scrapingbee_api_key}"
            f"&url={url}"
            f"&render_js=true"
            f"&premium_proxy=true"
            f"&country_code=it"
        )
        try:
            with httpx.Client(timeout=60) as client:
                r = client.get(api_url)
            r.raise_for_status()
            logger.info(
                "ScrapingBee API OK | status=%s | len=%s", r.status_code, len(r.text)
            )
            return r.text
        except Exception as exc:
            logger.warning("ScrapingBee API fallita: %s", exc)
            return None

    def _scrape_once(self, url: str, portal: str, headless: Optional[bool] = None, use_anti_bot: bool = False) -> ScraperResult:
        assert self._browser is not None, "Browser non inizializzato."

        proxy = None
        extra_headers = {
            "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "max-age=0",
        }
        if use_anti_bot and settings.scrapingbee_api_key:
            masked = settings.scrapingbee_api_key[:4] + "..." + settings.scrapingbee_api_key[-4:]
            logger.info("ScrapingBee anti-bot attivato (via API) | key=%s", masked)

        context: BrowserContext = self._browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1280, "height": 900},
            locale="it-IT",
            timezone_id="Europe/Rome",
            has_touch=True,
            color_scheme="light",
            device_scale_factor=1,
            bypass_csp=True,
            proxy=proxy,
            extra_http_headers=extra_headers,
        )

        # Blocca SOLO tracker e ads (non immagini/font che servono al rendering)
        def _route_handler(route):
            url_str = route.request.url
            if BLOCKED_REGEX.search(url_str):
                route.abort()
            else:
                route.continue_()

        context.route("**/*", _route_handler)

        page: Page = context.new_page()

        try:
            if use_anti_bot and settings.scrapingbee_api_key:
                html = self._fetch_via_scrapingbee_api(url)
                if html is None:
                    raise RuntimeError("ScrapingBee API non ha restituito contenuto")
                page.set_content(html, wait_until="domcontentloaded", timeout=settings.playwright_timeout)
                final_url = url
                status = 200
                logger.info("Pagina caricata via ScrapingBee API | status=%s | url=%s", status, final_url)
            else:
                response = page.goto(
                    url,
                    wait_until="load",
                    timeout=settings.playwright_timeout,
                )

                # Log utili per il debug
                final_url = page.url
                status = response.status if response else "N/A"
                logger.info("Pagina caricata | status=%s | url_finale=%s", status, final_url)

            # Aspetta che la rete si stabilizzi (contenuti JS dinamici)
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                logger.debug("networkidle non raggiunto, proseguo comunque")

            # Se il browser è visibile, dai tempo all'utente di risolvere eventuali captcha/anti-bot
            is_headless = headless if headless is not None else settings.playwright_headless
            if not is_headless:
                logger.info(
                    "Browser visibile attivo: pausa di 20s per interazione manuale (captcha/anti-bot). "
                    "Risolvi il controllo e attendi il proseguimento automatico..."
                )
                time.sleep(20)

            # Anti-detection: rimuovi il flag webdriver
            try:
                page.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                """)
            except Exception:
                pass

            # Accetta cookie
            self._accept_cookies(page)

            # Attesa random per sembrare umano
            time.sleep(_random_delay(2.0, 4.0))

            # Clicca "Mostra tutto" / "Leggi di più" se presente
            self._expand_read_more(page)

            # Scroll graduale per triggerare lazy-loading
            self._scroll_page(page)

            # Estrai testo
            text_content = self._extract_text(page, portal)
            page_title = page.title()

            # Se il testo è vuoto, logghiamo qualche info utile per debug
            if not text_content:
                body_length = page.evaluate("document.body.innerText.length")
                html_length = page.evaluate("document.documentElement.outerHTML.length")
                logger.warning(
                    "Testo estratto vuoto | body_innerText_len=%s | html_len=%s",
                    body_length,
                    html_length,
                )

            # Cattura screenshot come fallback per GPT-4o Vision
            screenshot_bytes = page.screenshot(full_page=False, type="png")
            screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

            return ScraperResult(
                url=url,
                portal=portal,
                text_content=text_content,
                screenshot_base64=screenshot_b64,
                page_title=page_title,
                success=True,
                metadata={
                    "user_agent": page.evaluate("navigator.userAgent"),
                    "final_url": final_url,
                    "status": status,
                },
            )
        finally:
            page.close()
            context.close()

    def _accept_cookies(self, page: Page) -> None:
        """Tenta di accettare il cookie banner se presente."""
        for selector in COOKIE_SELECTORS:
            try:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=3000):
                    btn.click(timeout=5000)
                    logger.debug("Cookie banner accettato con selettore: %s", selector)
                    time.sleep(1.0)
                    return
            except Exception:
                continue
        logger.debug("Nessun cookie banner trovato")

    def _expand_read_more(self, page: Page) -> None:
        """Clicca su eventuali bottoni 'Mostra tutto' / 'Leggi di più'."""
        for selector in READ_MORE_SELECTORS:
            try:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=2000):
                    btn.click(timeout=3000)
                    logger.debug("Testo espanso con selettore: %s", selector)
                    time.sleep(1.0)
                    return
            except Exception:
                continue

    def _scroll_page(self, page: Page) -> None:
        """Scorre la pagina gradualmente per attivare il lazy loading dei contenuti."""
        try:
            total_height = page.evaluate("document.body.scrollHeight")
            if not total_height or total_height <= 0:
                return
            steps = min(5, max(1, total_height // 800))
            step_size = total_height // steps
            for i in range(steps):
                page.evaluate(f"window.scrollTo(0, {step_size * (i + 1)})")
                time.sleep(_random_delay(0.5, 1.0))
            # Torna all'inizio
            page.evaluate("window.scrollTo(0, 0)")
            time.sleep(0.5)
        except Exception as e:
            logger.debug("Scroll parzialmente fallito: %s", e)

    def _extract_text(self, page: Page, portal: str) -> str:
        """
        Estrae il testo significativo dalla pagina.
        Prima prova con selettori specifici per portale, poi usa il body completo.
        """
        selectors = PORTAL_SELECTORS.get(portal, PORTAL_SELECTORS["default"])

        for selector in selectors:
            try:
                element = page.locator(selector).first
                if element.is_visible(timeout=5000):
                    text = element.inner_text(timeout=8000)
                    text = text.strip()
                    if len(text) > 200:
                        logger.debug(
                            "Testo estratto con selettore '%s' (%d caratteri)",
                            selector,
                            len(text),
                        )
                        return text[:8000]
            except Exception:
                continue

        # Fallback: body completo via innerText
        logger.warning("Fallback al body completo per portale: %s", portal)
        try:
            text = page.evaluate("document.body.innerText || ''")
            if text and len(text.strip()) > 0:
                return text.strip()[:8000]
        except Exception:
            pass

        # Ultimo fallback: html visibile
        try:
            text = page.inner_text("body")[:8000]
            return text.strip()
        except Exception:
            return ""


# ---------------------------------------------------------------------------
# Funzione pubblica asincrona (interfaccia per FastAPI)
# ---------------------------------------------------------------------------


def _scrape_sync(url: str, headless: Optional[bool] = None, use_anti_bot: bool = False) -> ScraperResult:
    """Helper sincrono che gestisce il ciclo di vita dello scraper."""
    scraper = _PropertyScraperSync()
    try:
        scraper.start(headless=headless, use_anti_bot=use_anti_bot)
        return scraper.scrape(url, headless=headless, use_anti_bot=use_anti_bot)
    finally:
        scraper.stop()


async def scrape_property(url: str, headless: Optional[bool] = None, use_anti_bot: bool = False) -> ScraperResult:
    """
    Funzione helper asincrona per usare lo scraper dagli endpoint FastAPI.
    Esegue Playwright in un thread separato per evitare conflitti con il loop asyncio.
    """
    return await asyncio.to_thread(_scrape_sync, url, headless, use_anti_bot)
