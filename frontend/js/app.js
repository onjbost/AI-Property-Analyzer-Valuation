/* ==========================================
   AI Property Analyzer — SPA Logic
   ========================================== */

const API_BASE = '';

// DOM refs
const els = {
  urlInput: document.getElementById('url-input'),
  btnAnalyze: document.getElementById('btn-analyze'),
  btnText: document.querySelector('.btn-text'),
  btnLoader: document.querySelector('.btn-loader'),
  searchContainer: document.getElementById('search-container'),
  resultsContainer: document.getElementById('results-container'),
  screenshotCard: document.getElementById('screenshot-card'),
  screenshotImg: document.getElementById('screenshot-img'),
  btnSettings: document.getElementById('btn-settings'),
  btnBack: document.getElementById('btn-back'),
  btnSaveSettings: document.getElementById('btn-save-settings'),
  pageHome: document.getElementById('page-home'),
  pageSettings: document.getElementById('page-settings'),
  pageManual: document.getElementById('page-manual'),
  settingsStatus: document.getElementById('settings-status'),
  settingProvider: document.getElementById('setting-provider'),
  settingApiKey: document.getElementById('setting-api-key'),
  settingModel: document.getElementById('setting-model'),
  settingBaseUrl: document.getElementById('setting-base-url'),
  groupBaseUrl: document.getElementById('group-base-url'),
  settingHeadless: document.getElementById('setting-headless'),
  settingAntiBot: document.getElementById('setting-anti-bot'),
  omiZipUpload: document.getElementById('omi-zip-upload'),
  omiSemestreInput: document.getElementById('omi-semestre-input'),
  btnUpdateOmi: document.getElementById('btn-update-omi'),
  omiUpdateStatus: document.getElementById('omi-update-status'),
  btnManual: document.getElementById('btn-manual'),
  btnBackManual: document.getElementById('btn-back-manual'),
  btnEvaluateManual: document.getElementById('btn-evaluate-manual'),

  // Verdict
  verdictCard: document.getElementById('verdict-card'),
  verdictBadge: document.getElementById('verdict-badge'),
  verdictIcon: document.getElementById('verdict-icon'),
  verdictText: document.getElementById('verdict-text'),
  scoreProgress: document.getElementById('score-progress'),
  scoreNumber: document.getElementById('score-number'),
  verdictTitle: document.getElementById('verdict-title'),
  verdictDescription: document.getElementById('verdict-description'),
  pillTime: document.getElementById('pill-time'),
  pillPortal: document.getElementById('pill-portal'),

  // Property
  propPrezzo: document.getElementById('prop-prezzo'),
  propMq: document.getElementById('prop-mq'),
  propPrezzoMq: document.getElementById('prop-prezzo-mq'),
  propLocali: document.getElementById('prop-locali'),
  propCamere: document.getElementById('prop-camere'),
  propBagni: document.getElementById('prop-bagni'),
  propPiano: document.getElementById('prop-piano'),
  propClasse: document.getElementById('prop-classe'),
  propAnno: document.getElementById('prop-anno'),
  propTipologia: document.getElementById('prop-tipologia'),
  propCitta: document.getElementById('prop-citta'),
  propZona: document.getElementById('prop-zona'),
  propIndirizzo: document.getElementById('prop-indirizzo'),

  // OMI
  omiZona: document.getElementById('omi-zona'),
  omiCitta: document.getElementById('omi-citta'),
  omiMin: document.getElementById('omi-min'),
  omiMax: document.getElementById('omi-max'),
  omiMedio: document.getElementById('omi-medio'),
  omiScostamento: document.getElementById('omi-scostamento'),
  omiSemestre: document.getElementById('omi-semestre'),
  omiFonte: document.getElementById('omi-fonte'),
  omiNote: document.getElementById('omi-note'),
  omiNoteRow: document.getElementById('omi-note-row'),

  // Sentiment
  sentimentCard: document.getElementById('sentiment-card'),
  strengthsList: document.getElementById('strengths-list'),
  weaknessesList: document.getElementById('weaknesses-list'),
  sentimentTotalRow: document.getElementById('sentiment-total-row'),
  sentimentTotal: document.getElementById('sentiment-total'),

  // Adjusted (inside price-compare card)
  adjustedCol: document.getElementById('adjusted-col'),
  adjustedPrezzo: document.getElementById('adjusted-prezzo'),
  adjustedBase: document.getElementById('adjusted-base'),
  adjustedAggiustamento: document.getElementById('adjusted-aggiustamento'),
  adjustedScostamento: document.getElementById('adjusted-scostamento'),
  adjustedVerdict: document.getElementById('adjusted-verdict'),
};

// Helpers
const fmtMoney = (n) => {
  if (n === null || n === undefined) return '--';
  return new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(n);
};

const fmtNum = (n) => (n === null || n === undefined ? '--' : n.toLocaleString('it-IT'));

const fmtPct = (n) => {
  if (n === null || n === undefined) return '--';
  const sign = n > 0 ? '+' : '';
  return `${sign}${n.toFixed(2)}%`;
};

const showToast = (message, type = 'error') => {
  const existing = document.querySelector('.toast');
  if (existing) existing.remove();
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `<i data-lucide="${type === 'error' ? 'alert-circle' : 'check-circle'}"></i><span>${message}</span>`;
  document.body.appendChild(toast);
  lucide.createIcons({ nodes: [toast] });
  requestAnimationFrame(() => toast.classList.add('show'));
  setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => toast.remove(), 400);
  }, 4000);
};

const setLoading = (loading) => {
  els.btnAnalyze.disabled = loading;
  els.btnText.classList.toggle('hidden', loading);
  els.btnLoader.classList.toggle('hidden', !loading);
  els.urlInput.disabled = loading;
};

const animateScore = (target) => {
  const circumference = 2 * Math.PI * 52; // ~326.726
  const offset = circumference - (target / 100) * circumference;
  els.scoreProgress.style.strokeDashoffset = offset;

  let current = 0;
  const duration = 1200;
  const start = performance.now();
  const tick = (now) => {
    const elapsed = now - start;
    const progress = Math.min(elapsed / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    current = Math.round(eased * target * 10) / 10;
    els.scoreNumber.textContent = current;
    if (progress < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
};

// Routing
const showPage = (name) => {
  els.pageHome.classList.toggle('active', name === 'home');
  els.pageSettings.classList.toggle('active', name === 'settings');
  els.pageManual.classList.toggle('active', name === 'manual');
  if (name === 'home') {
    document.title = 'AI Property Analyzer';
  } else if (name === 'settings') {
    document.title = 'Impostazioni — AI Property Analyzer';
    loadSettings();
  } else if (name === 'manual') {
    document.title = 'Valutazione Manuale — AI Property Analyzer';
  }
  lucide.createIcons();
};

// Settings
const MODEL_OPTIONS = {
  openai: [
    { value: 'gpt-4o', label: 'GPT-4o (consigliato)' },
    { value: 'gpt-4o-mini', label: 'GPT-4o Mini' },
    { value: 'gpt-4-turbo', label: 'GPT-4 Turbo' },
  ],
  moonshot: [
    { value: 'moonshot-v1-8k', label: 'Moonshot v1-8k' },
    { value: 'moonshot-v1-32k', label: 'Moonshot v1-32k' },
    { value: 'moonshot-v1-128k', label: 'Moonshot v1-128k' },
  ],
  nvidia: [
    { value: 'meta/llama-4-maverick-17b-128e-instruct', label: 'Llama 4 Maverick 17B (consigliato)' },
    { value: 'meta/llama-3.1-405b-instruct', label: 'Llama 3.1 405B' },
    { value: 'meta/llama-3.1-70b-instruct', label: 'Llama 3.1 70B' },
    { value: 'meta/llama-3.1-8b-instruct', label: 'Llama 3.1 8B' },
    { value: 'nvidia/nemotron-4-340b-instruct', label: 'Nemotron-4 340B' },
    { value: 'mistralai/mistral-large-2-instruct', label: 'Mistral Large 2' },
    { value: 'google/gemma-2-27b-it', label: 'Gemma 2 27B' },
    { value: 'google/gemma-2-9b-it', label: 'Gemma 2 9B' },
  ],
};

const populateModels = (provider) => {
  const current = els.settingModel.value;
  els.settingModel.innerHTML = '';
  MODEL_OPTIONS[provider].forEach((opt) => {
    const option = document.createElement('option');
    option.value = opt.value;
    option.textContent = opt.label;
    els.settingModel.appendChild(option);
  });
  // Tenta di mantenere selezione precedente se valida
  if (MODEL_OPTIONS[provider].some((o) => o.value === current)) {
    els.settingModel.value = current;
  }
};

const loadSettings = () => {
  const provider = localStorage.getItem('ai_provider') || 'openai';
  els.settingProvider.value = provider;
  populateModels(provider);
  els.settingApiKey.value = localStorage.getItem('ai_api_key') || '';
  const defaultModel =
    provider === 'openai' ? 'gpt-4o' :
    provider === 'nvidia' ? 'meta/llama-4-maverick-17b-128e-instruct' :
    'moonshot-v1-8k';
  els.settingModel.value = localStorage.getItem('ai_model') || defaultModel;
  els.settingBaseUrl.value = localStorage.getItem('ai_base_url') || '';
  const headlessVal = localStorage.getItem('ai_headless');
  els.settingHeadless.value = headlessVal === null ? 'true' : headlessVal;
  const antiBotVal = localStorage.getItem('ai_anti_bot');
  els.settingAntiBot.value = antiBotVal === null ? 'false' : antiBotVal;
};

const saveSettings = () => {
  const provider = els.settingProvider.value;
  const key = els.settingApiKey.value.trim();
  const model = els.settingModel.value;
  const baseUrl = els.settingBaseUrl.value.trim();

  localStorage.setItem('ai_provider', provider);
  if (key) localStorage.setItem('ai_api_key', key);
  else localStorage.removeItem('ai_api_key');
  localStorage.setItem('ai_model', model);
  if (baseUrl) localStorage.setItem('ai_base_url', baseUrl);
  else localStorage.removeItem('ai_base_url');

  localStorage.setItem('ai_headless', els.settingHeadless.value);
  localStorage.setItem('ai_anti_bot', els.settingAntiBot.value);

  els.settingsStatus.classList.remove('hidden');
  lucide.createIcons();
  setTimeout(() => els.settingsStatus.classList.add('hidden'), 2500);
};

// Render report
const renderReport = (data) => {
  const pd = data.property_data;
  const om = data.omi_comparison;

  // Verdict
  const verdict = data.verdict.toLowerCase();
  const isAffare = verdict === 'affare';
  const isSoprastimato = verdict === 'soprastimato';

  els.verdictBadge.className = `verdict-badge ${verdict}`;
  els.verdictText.textContent = data.verdict;
  els.verdictIcon.setAttribute('data-lucide', isAffare ? 'trending-down' : isSoprastimato ? 'trending-up' : 'minus');
  els.verdictTitle.textContent = isAffare ? 'Ottimo affare!' : isSoprastimato ? 'Attenzione: sopra il mercato' : 'Prezzo di mercato';
  els.verdictDescription.textContent = data.verdict_description;

  // Score
  animateScore(data.investment_score);

  // Meta pills
  els.pillTime.innerHTML = `<i data-lucide="clock"></i> <span>${data.processing_time_ms || '--'} ms</span>`;
  els.pillPortal.innerHTML = `<i data-lucide="globe"></i> <span>${pd.portal || '--'}</span>`;

  // Property
  els.propPrezzo.textContent = fmtMoney(pd.prezzo);
  els.propMq.textContent = pd.mq ? `${fmtNum(pd.mq)} m²` : '--';
  els.propPrezzoMq.textContent = pd.prezzo_mq ? `${fmtNum(pd.prezzo_mq)} €/m²` : '--';
  els.propLocali.textContent = fmtNum(pd.locali);
  els.propCamere.textContent = fmtNum(pd.camere);
  els.propBagni.textContent = fmtNum(pd.bagni);
  els.propPiano.textContent = pd.piano || '--';
  els.propClasse.textContent = pd.classe_energetica || '--';
  els.propAnno.textContent = pd.anno_costruzione || '--';
  els.propTipologia.textContent = pd.tipologia || '--';
  els.propCitta.textContent = pd.citta || '--';
  els.propZona.textContent = pd.zona || '--';
  els.propIndirizzo.textContent = pd.indirizzo || '--';

  // OMI
  els.omiZona.textContent = om.zona_omi || '--';
  els.omiCitta.textContent = om.citta_omi || '--';
  els.omiMin.textContent = om.prezzo_min_omi ? `${fmtNum(om.prezzo_min_omi)} €/m²` : '--';
  els.omiMax.textContent = om.prezzo_max_omi ? `${fmtNum(om.prezzo_max_omi)} €/m²` : '--';
  els.omiMedio.textContent = om.prezzo_medio_omi ? fmtNum(om.prezzo_medio_omi) : '--';
  const scost = om.scostamento_percentuale;
  els.omiScostamento.textContent = fmtPct(scost);
  els.omiScostamento.style.color = scost === null || scost === undefined ? '' : scost < 0 ? 'var(--success)' : scost > 0 ? 'var(--danger)' : 'var(--warning)';
  els.omiSemestre.textContent = om.semestre_omi || '--';
  els.omiFonte.textContent = om.fonte || 'Agenzia delle Entrate';
  if (om.note) {
    els.omiNote.textContent = om.note;
    els.omiNoteRow.classList.remove('hidden');
  } else {
    els.omiNote.textContent = '';
    els.omiNoteRow.classList.add('hidden');
  }

  // Screenshot
  if (data.screenshot_base64) {
    els.screenshotImg.src = `data:image/png;base64,${data.screenshot_base64}`;
    els.screenshotCard.classList.remove('hidden');
  } else {
    els.screenshotCard.classList.add('hidden');
    els.screenshotImg.src = '';
  }

  // Sentiment & Adjusted
  renderSentiment(data.sentiment_analysis);
  renderAdjusted(data.adjusted_comparison);

  // Show results
  els.resultsContainer.classList.remove('hidden');
  lucide.createIcons();
};

// Render sentiment analysis
const renderSentiment = (sentiment) => {
  if (!sentiment) {
    els.sentimentCard.classList.add('hidden');
    return;
  }

  const strengths = sentiment.strengths || [];
  const weaknesses = sentiment.weaknesses || [];

  if (strengths.length === 0 && weaknesses.length === 0) {
    els.sentimentCard.classList.add('hidden');
    return;
  }

  els.sentimentCard.classList.remove('hidden');

  const makeItem = (item, positive) => {
    const li = document.createElement('li');
    li.className = 'sentiment-item';
    const badgeClass = positive ? 'impact-positive' : 'impact-negative';
    const sign = item.price_impact_percent > 0 ? '+' : '';
    li.innerHTML = `<span>${escapeHtml(item.description)}</span><span class="impact-badge ${badgeClass}">${sign}${item.price_impact_percent.toFixed(1)}%</span>`;
    return li;
  };

  els.strengthsList.innerHTML = '';
  els.weaknessesList.innerHTML = '';

  if (strengths.length > 0) {
    strengths.forEach((s) => els.strengthsList.appendChild(makeItem(s, true)));
    document.getElementById('strengths-section').classList.remove('hidden');
  } else {
    document.getElementById('strengths-section').classList.add('hidden');
  }

  if (weaknesses.length > 0) {
    weaknesses.forEach((w) => els.weaknessesList.appendChild(makeItem(w, false)));
    document.getElementById('weaknesses-section').classList.remove('hidden');
  } else {
    document.getElementById('weaknesses-section').classList.add('hidden');
  }

  // Totale
  const total = [...strengths, ...weaknesses].reduce((sum, i) => sum + (i.price_impact_percent || 0), 0);
  if (total !== 0) {
    els.sentimentTotalRow.classList.remove('hidden');
    const sign = total > 0 ? '+' : '';
    els.sentimentTotal.textContent = `${sign}${total.toFixed(1)}%`;
    els.sentimentTotal.style.color = total > 0 ? 'var(--success)' : total < 0 ? 'var(--danger)' : 'var(--text-primary)';
  } else {
    els.sentimentTotalRow.classList.add('hidden');
  }
};

// Render adjusted price comparison (inside price-compare card)
const renderAdjusted = (adjusted) => {
  if (!adjusted) {
    els.adjustedCol.classList.add('hidden');
    return;
  }

  els.adjustedCol.classList.remove('hidden');
  els.adjustedPrezzo.textContent = fmtMoney(adjusted.prezzo_corretto);
  els.adjustedBase.textContent = fmtMoney(adjusted.prezzo_base_omi);

  const adj = adjusted.totale_aggiustamento_percentuale;
  const adjSign = adj > 0 ? '+' : '';
  els.adjustedAggiustamento.textContent = `${adjSign}${adj.toFixed(1)}%`;
  els.adjustedAggiustamento.style.color = adj > 0 ? 'var(--success)' : adj < 0 ? 'var(--danger)' : 'var(--text-primary)';

  const scost = adjusted.scostamento_percentuale;
  els.adjustedScostamento.textContent = fmtPct(scost);
  els.adjustedScostamento.style.color = scost === null || scost === undefined ? '' : scost < 0 ? 'var(--success)' : scost > 0 ? 'var(--danger)' : 'var(--warning)';

  const v = adjusted.verdict;
  els.adjustedVerdict.textContent = v;
  els.adjustedVerdict.style.color = v === 'AFFARE' ? 'var(--success)' : v === 'SOPRASTIMATO' ? 'var(--danger)' : 'var(--warning)';
};

const escapeHtml = (text) => {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
};

// Manual evaluate
const evaluateManual = async () => {
  const payload = {
    prezzo: parseFloat(document.getElementById('manual-prezzo').value),
    mq: parseFloat(document.getElementById('manual-mq').value),
    citta: document.getElementById('manual-citta').value.trim(),
    zona: document.getElementById('manual-zona').value.trim() || null,
    locali: parseInt(document.getElementById('manual-locali').value) || null,
    classe_energetica: document.getElementById('manual-classe').value || null,
    tipologia: document.getElementById('manual-tipologia').value.trim() || null,
    camere: parseInt(document.getElementById('manual-camere').value) || null,
    bagni: parseInt(document.getElementById('manual-bagni').value) || null,
    piano: document.getElementById('manual-piano').value.trim() || null,
    anno_costruzione: parseInt(document.getElementById('manual-anno').value) || null,
    indirizzo: document.getElementById('manual-indirizzo').value.trim() || null,
    url: document.getElementById('manual-url').value.trim() || null,
  };

  if (!payload.prezzo || !payload.mq || !payload.citta) {
    showToast('Prezzo, superficie e città sono obbligatori');
    return;
  }

  els.btnEvaluateManual.disabled = true;
  els.btnEvaluateManual.textContent = 'Calcolo in corso...';

  try {
    const res = await fetch(`${API_BASE}/api/v1/evaluate-manual`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const errBody = await res.json();
      throw new Error(errBody.detail?.message || 'Errore valutazione');
    }
    const data = await res.json();
    showPage('home');
    els.searchContainer.classList.add('compact');
    renderReport(data);
  } catch (err) {
    showToast(err.message || 'Errore di rete');
  } finally {
    els.btnEvaluateManual.disabled = false;
    els.btnEvaluateManual.textContent = 'Calcola valutazione';
  }
};

// Analyze
const analyze = async () => {
  const url = els.urlInput.value.trim();
  if (!url) {
    showToast('Inserisci un URL di annuncio');
    return;
  }
  if (!url.startsWith('http')) {
    showToast('Inserisci un URL valido (https://...)');
    return;
  }

  setLoading(true);

  // Reset UI
  els.resultsContainer.classList.add('hidden');
  els.searchContainer.classList.add('compact');
  els.scoreProgress.style.strokeDashoffset = 326.726;
  els.scoreNumber.textContent = '0';

  const savedProvider = localStorage.getItem('ai_provider');
  const savedKey = localStorage.getItem('ai_api_key');
  const savedModel = localStorage.getItem('ai_model');
  const savedBaseUrl = localStorage.getItem('ai_base_url');
  const savedHeadless = localStorage.getItem('ai_headless');
  const savedAntiBot = localStorage.getItem('ai_anti_bot');

  const payload = {
    url,
    provider: savedProvider || 'openai',
    api_key: savedKey || undefined,
    model: savedModel || undefined,
    base_url: savedBaseUrl || undefined,
    headless: savedHeadless === 'true',
    use_anti_bot: savedAntiBot === 'true',
  };
  // Rimuovi chiavi undefined per non sporcare il payload
  Object.keys(payload).forEach((k) => {
    if (payload[k] === undefined) delete payload[k];
  });

  try {
    const res = await fetch(`${API_BASE}/api/v1/evaluate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      let detail = `Errore ${res.status}`;
      try {
        const errBody = await res.json();
        detail = errBody.detail?.message || errBody.detail || detail;
      } catch (_) {}
      throw new Error(detail);
    }

    const data = await res.json();
    renderReport(data);
  } catch (err) {
    showToast(err.message || 'Errore di rete');
    // Se l'errore avviene subito, lascia la search bar compatta ma mostra il messaggio
  } finally {
    setLoading(false);
  }
};

// Upload OMI dataset
const updateOmiDataset = async () => {
  const file = els.omiZipUpload.files[0];
  if (!file) {
    showToast('Seleziona un file ZIP ufficiale Agenzia delle Entrate');
    return;
  }
  if (!file.name.toLowerCase().endsWith('.zip')) {
    showToast('Il file deve essere un archivio ZIP');
    return;
  }

  els.btnUpdateOmi.disabled = true;
  els.btnUpdateOmi.textContent = 'Aggiornamento in corso...';

  const formData = new FormData();
  formData.append('file', file);
  const semestre = els.omiSemestreInput.value.trim();
  if (semestre) formData.append('semestre', semestre);

  try {
    const res = await fetch(`${API_BASE}/api/v1/admin/update-omi`, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) {
      const errBody = await res.json();
      throw new Error(errBody.detail || `Errore ${res.status}`);
    }
    const data = await res.json();
    els.omiUpdateStatus.classList.remove('hidden');
    els.omiUpdateStatus.querySelector('span').textContent =
      `Dataset aggiornato: ${data.rows?.toLocaleString('it-IT')} righe, ${data.cities?.toLocaleString('it-IT')} città`;
    lucide.createIcons();
    setTimeout(() => els.omiUpdateStatus.classList.add('hidden'), 4000);
    els.omiZipUpload.value = '';
    els.omiSemestreInput.value = '';
  } catch (err) {
    showToast(err.message || 'Errore durante l\'aggiornamento del dataset');
  } finally {
    els.btnUpdateOmi.disabled = false;
    els.btnUpdateOmi.textContent = 'Aggiorna dataset OMI';
  }
};

// Event bindings
document.addEventListener('DOMContentLoaded', () => {
  lucide.createIcons();

  els.btnAnalyze.addEventListener('click', analyze);
  els.urlInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') analyze();
  });

  els.btnSettings.addEventListener('click', () => showPage('settings'));
  els.btnManual.addEventListener('click', () => showPage('manual'));
  els.btnBack.addEventListener('click', () => showPage('home'));
  els.btnBackManual.addEventListener('click', () => showPage('home'));
  els.btnSaveSettings.addEventListener('click', saveSettings);
  els.btnEvaluateManual.addEventListener('click', evaluateManual);
  els.btnUpdateOmi.addEventListener('click', updateOmiDataset);
  els.settingProvider.addEventListener('change', () => {
    populateModels(els.settingProvider.value);
  });
});
