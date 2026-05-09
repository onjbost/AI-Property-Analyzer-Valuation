# AI Property Analyzer & Valuation

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)

Uno strumento intelligente per valutare in tempo reale la convenienza degli investimenti immobiliari in Italia.

> ⚠️ **Disclaimer**
>
> Le stime fornite da questo tool sono **puramente indicative** e si basano su dati pubblici (OMI — Osservatorio Mercato Immobiliare dell'Agenzia delle Entrate) e su analisi effettuate da modelli di intelligenza artificiale.
>
> **Questo tool non sostituisce in alcun modo la perizia di un tecnico abilitato** (geometra, architetto, ingegnere, agente immobiliare). Il valore reale di un immobile dipende da innumerevoli fattori che solo un esperto può valutare con precisione (stato di manutenzione, conformità urbanistica, potenzialità edificatorie, condizioni di mercato locali, ecc.).
>
> Lo scopo di questo progetto è **aiutare** chi è alla ricerca di un immobile, chi desidera venderlo o chi vuole investire, fornendo un primo orientamento sui prezzi ideali di riferimento. Si consiglia vivamente di integrare queste informazioni con una vera e propria stima professionale prima di prendere qualsiasi decisione economica.

## Business Value

Gli investitori immobiliari perdono ore a confrontare annunci manualmente. Questo tool automatizza l'analisi, identificando istantaneamente gli immobili *underpriced* rispetto alla media di mercato (OMI), riducendo il tempo di scouting del 90%.

## Caratteristiche

- **Scraping Resiliente**: Playwright con supporto proxy anti-bot (ScrapingBee) e fallback screenshot quando i siti bloccano il crawler.
- **Estrazione AI Multi-Provider**: Supporta OpenAI (GPT-4o), Moonshot AI (Kimi) e **NVIDIA Build** (Llama 3.1, Nemotron, Mistral, Gemma — modelli free) per estrarre dati strutturati da annunci non strutturati.
- **Valutazione Manuale**: Inserisci direttamente i dati dell'immobile (senza scraping) per ottenere un report immediato.
- **Confronto OMI Completo**: Dataset aggiornabile con quotazioni ufficiali Agenzia delle Entrate per tutti i comuni italiani.
- **Fallback Geografico**: Se un comune non ha dati OMI, il sistema trova automaticamente il comune più vicino geograficamente.
- **Investment Score**: Algoritmo proprietario per il calcolo del potenziale di rendimento (0-100).
- **WebApp Moderna**: Interfaccia glassmorphism responsive con routing SPA, impostazioni persistenti e upload dataset OMI.

---

## Tech Stack

| Componente | Tecnologia |
|------------|------------|
| Backend | Python 3.11+, FastAPI, Pydantic |
| Scraping | Playwright (sync in thread) |
| AI / LLM | OpenAI GPT-4o, Moonshot AI (Kimi), NVIDIA Build via AsyncOpenAI |
| OMI Dataset | CSV ufficiale Agenzia delle Entrate (aggiornabile via webapp) |
| Frontend | Vanilla JS, HTML5, CSS3 (Glassmorphism) |
| Proxy | ScrapingBee API (opzionale) |

---

## Quick Start

### 1. Clona il repository

```bash
git clone https://github.com/tuo-username/ai-property-analyzer.git
cd ai-property-analyzer
```

### 2. Crea e attiva l'ambiente virtuale

```bash
python -m venv .venv
# Windows
.\.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
```

### 3. Installa le dipendenze

```bash
pip install -r requirements.txt
```

### 4. Installa il browser Playwright

```bash
python -m playwright install chromium
```

### 5. Configura le variabili d'ambiente

```bash
cp .env.example .env
```

Modifica `.env` inserendo almeno una chiave AI:

```env
# OpenAI (obbligatoria se usi OpenAI)
OPENAI_API_KEY=sk-...

# Moonshot AI (obbligatoria se usi Moonshot)
MOONSHOT_API_KEY=sk-...

# NVIDIA Build (obbligatoria se usi NVIDIA — ottieni key gratuita su https://build.nvidia.com)
NVIDIA_API_KEY=nvapi-...

# ScrapingBee (opzionale, per proxy anti-bot)
SCRAPINGBEE_API_KEY=...
```

### 6. Avvia il server

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

L'API sarà disponibile su `http://localhost:8001` e la WebApp su `http://localhost:8001/`.

---

## Tutorial API

### Valutazione automatica (con scraping)

```http
POST /api/v1/evaluate
Content-Type: application/json
```

**Body:**

```json
{
  "url": "https://www.immobiliare.it/annunci/123456789/",
  "provider": "openai",
  "api_key": "sk-...",
  "model": "gpt-4o",
  "headless": true,
  "use_anti_bot": false
}
```

| Campo | Tipo | Default | Descrizione |
|-------|------|---------|-------------|
| `url` | string | — | **Obbligatorio** — URL annuncio (Immobiliare.it / Idealista.it) |
| `provider` | string | `openai` | Provider AI: `openai`, `moonshot` o `nvidia` |
| `api_key` | string | `.env` | Chiave API personalizzata |
| `model` | string | `gpt-4o` / `moonshot-v1-8k` | Modello LLM |
| `headless` | bool | `true` | `false` = browser visibile (anti-bot) |
| `use_anti_bot` | bool | `false` | Attiva proxy ScrapingBee |
| `base_url` | string | — | URL base personalizzato per API AI |

### Valutazione manuale (senza scraping)

```http
POST /api/v1/evaluate-manual
Content-Type: application/json
```

**Body:**

```json
{
  "prezzo": 200000,
  "mq": 100,
  "citta": "Roma",
  "zona": "Centro",
  "locali": 3,
  "classe_energetica": "C",
  "tipologia": "Appartamento"
}
```

### Aggiornamento dataset OMI (admin)

```http
POST /api/v1/admin/update-omi
Content-Type: multipart/form-data
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `file` | file | ZIP ufficiale Agenzia delle Entrate (`QI_*_VALORI.csv`) |
| `semestre` | string | Opzionale — es. `2025-II` |

Puoi anche aggiornare il dataset direttamente dalla WebApp, nella sezione **Impostazioni**.

---

## WebApp Frontend

L'applicazione include una **Single Page Application** moderna con design glassmorphism accessibile alla root del server (`http://localhost:8001/`).

### Funzionalità

- **Home**: inserisci l'URL di un annuncio e premi *Analizza con l'AI*
- **Valutazione Manuale**: inserisci direttamente i dati per un report senza scraping
- **Impostazioni**:
  - Scegli provider AI (OpenAI / Moonshot / NVIDIA Build)
  - Attiva/disattiva proxy anti-bot e modalità headless
  - **Carica ZIP OMI** per aggiornare le quotazioni ufficiali
- **Report interattivi**: verdetto, investment score, dati immobile, confronto OMI, note proxy

---

## Architettura

```
URL Annuncio
     │
     ▼
┌─────────────┐
│  Scraping   │  ← Playwright (+ ScrapingBee proxy opzionale)
│ (Playwright)│
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ Estrazione  │  ← GPT-4o / Moonshot (testo o visione screenshot)
│     AI      │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Confronto  │  ← Dataset OMI ufficiale (fuzzy match + fallback geografico)
│    OMI      │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│    Report   │  ← Investment Score + Verdetto
│   Finale    │
└─────────────┘
```

---

## Configurazione avanzata

### Variabili d'ambiente

| Variabile | Descrizione | Default |
|-----------|-------------|---------|
| `OPENAI_API_KEY` | Chiave API OpenAI | — |
| `OPENAI_MODEL` | Modello OpenAI | `gpt-4o` |
| `MOONSHOT_API_KEY` | Chiave API Moonshot | — |
| `MOONSHOT_BASE_URL` | Endpoint Moonshot | `https://api.moonshot.ai/v1` |
| `MOONSHOT_MODEL` | Modello Moonshot | `moonshot-v1-8k` |
| `NVIDIA_API_KEY` | Chiave API NVIDIA Build | — |
| `NVIDIA_BASE_URL` | Endpoint NVIDIA | `https://integrate.api.nvidia.com/v1` |
| `NVIDIA_MODEL` | Modello NVIDIA | `meta/llama-3.1-405b-instruct` |
| `SCRAPINGBEE_API_KEY` | Chiave proxy ScrapingBee | — |
| `PLAYWRIGHT_HEADLESS` | Browser headless di default | `true` |
| `PLAYWRIGHT_TIMEOUT` | Timeout scraping (ms) | `30000` |
| `OMI_CSV_PATH` | Percorso dataset OMI | `app/data/omi_full.csv` |

---

## Limitazioni note

- **Immobiliare.it** ha protezioni anti-bot aggressive. Se lo scraping fallisce:
  - Disattiva **Modalità headless** nelle Impostazioni
  - Attiva **Proxy anti-bot** (richiede ScrapingBee)
  - Usa **Valutazione Manuale**
- Quando il testo non è estraibile, viene restituito uno screenshot per verifica visiva
- Alcuni comuni piccolissimi potrebbero non avere zone OMI; in tal caso il sistema usa il **comune geograficamente più vicino**

---

## Requisiti

- Python 3.11+
- Chiave API OpenAI, Moonshot AI **o** NVIDIA Build
- Playwright Chromium installato (`python -m playwright install chromium`)

---

## Licenza

Questo progetto è rilasciato sotto licenza [MIT](LICENSE).

---

## Contributi

Contributi, segnalazioni bug e pull request sono benvenuti! Per modifiche importanti, apri prima una issue per discutere cosa vorresti cambiare.
