/* OnlyFans DL DSM UI. No external dependencies; all data stays on the NAS. */
(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const t = (key, vars) => (window.ofdlI18n ? window.ofdlI18n.t(key, vars) : key);
  const ACTIVE = new Set(['queued', 'running', 'paused']);
  const STATUS_TEXT = {
    queued: 'Wartet', running: 'Läuft', paused: 'Pausiert',
    completed: 'Fertig', failed: 'Fehler', cancelled: 'Abgebrochen',
  };
  const KIND_TEXT = {
    test_session: 'Sitzungstest', subscriptions: 'Abonnements',
    download: 'Download', preview: 'Vorschau',
    offers_scan: 'Angebote suchen', free_renew: 'Kostenlose Wiederanmeldung',
  };

  const state = {
    csrf: '',
    settings: null,
    status: null,
    activeJob: null,
    lastJob: null,
    lastEventId: 0,
    finishedJobId: null,
    previewRequested: false,
    selectedCreators: new Set(),
    creatorPage: 1,
    creatorPages: 1,
    creatorTotal: 0,
    creatorQuery: '',
    folderPath: '',
    folderParent: null,
    folderRoot: '',
    polling: false,
    settingsLoaded: false,
    displayJobId: null,
    eventsInitial: true,
    lastSync: 0,
    failures: 0,
    authExpired: false,
    offersPage: 1,
    needsJobPoll: false,
    creatorRequest: 0,
    folderRequest: 0,
  };

  /* ------------------------------------------------------------------ */
  /* Utilities                                                          */
  /* ------------------------------------------------------------------ */

  function toast(message, kind = '') {
    const box = $('toast');
    box.textContent = String(message || '');
    box.className = `toast ${kind}`.trim();
    box.hidden = false;
    clearTimeout(toast._timer);
    toast._timer = setTimeout(() => { box.hidden = true; }, 6000);
  }

  function setBusy(button, busy, label) {
    if (!button) return;
    if (busy) {
      if (!button.dataset.label) button.dataset.label = button.textContent;
      button.disabled = true;
      if (label) button.textContent = label;
    } else {
      button.disabled = false;
      if (button.dataset.label) button.textContent = button.dataset.label;
    }
  }

  function formatBytes(value) {
    let amount = Number(value || 0);
    if (!Number.isFinite(amount) || amount <= 0) return '0 B';
    const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB'];
    let index = 0;
    while (amount >= 1024 && index < units.length - 1) { amount /= 1024; index += 1; }
    return index === 0 ? `${Math.round(amount)} B` : `${amount.toFixed(1)} ${units[index]}`;
  }

  function formatDuration(seconds) {
    let value = Math.max(0, Number(seconds || 0));
    const days = Math.floor(value / 86400); value -= days * 86400;
    const hours = Math.floor(value / 3600); value -= hours * 3600;
    const minutes = Math.floor(value / 60);
    if (days) return `${days} d ${hours} h`;
    if (hours) return `${hours} h ${minutes} min`;
    if (minutes) return `${minutes} min`;
    return `${Math.floor(value)} s`;
  }

  function formatDate(value) {
    if (!value) return '–';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString(locale(), {
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit',
    });
  }

  function formatTime(value) {
    if (!value) return '–';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleTimeString(locale(), { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }

  function locale() {
    return window.ofdlI18n ? window.ofdlI18n.getLanguage() : 'de';
  }

  function splitProfiles(text) {
    const seen = new Set();
    const result = [];
    for (const token of String(text || '').split(/[\s,;]+/)) {
      const name = token.trim().replace(/^@/, '').toLowerCase();
      if (name && !seen.has(name)) { seen.add(name); result.push(name); }
    }
    return result;
  }

  function statusClass(status) {
    if (status === 'completed') return 'ok';
    if (status === 'failed') return 'bad';
    if (status === 'cancelled' || status === 'paused') return 'warn';
    return '';
  }

  async function api(path, options = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 12000);
    const init = {
      ...options,
      credentials: 'same-origin',
      headers: { Accept: 'application/json', ...(options.headers || {}) },
      signal: controller.signal,
      cache: 'no-store',
    };
    if (state.csrf) init.headers['X-CSRF-Token'] = state.csrf;
    if (init.body && typeof init.body !== 'string') {
      init.headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(init.body);
    }
    let response;
    let data = null;
    try {
      response = await fetch(path, init);
      const text = await response.text();
      try { data = JSON.parse(text); } catch (_) { /* Report malformed responses below. */ }
    } finally { clearTimeout(timer); }
    const type = response.headers.get('Content-Type') || '';
    if (type.includes('application/json')) {
      // Already decoded under the same timeout as the request.
    }
    if (response.status === 401) {
      window.location.replace('/login');
      state.authExpired = true;
      const error = new Error(t('Anmeldung abgelaufen. Bitte erneut anmelden.'));
      error.status = 401;
      throw error;
    }
    if (!response.ok) {
      const message = (data && data.error) || `HTTP ${response.status}`;
      const error = new Error(t(message));
      error.status = response.status;
      error.data = data;
      throw error;
    }
    if (!data || typeof data !== 'object' || Array.isArray(data)) {
      const error = new Error(t('Ungültige Serverantwort. Erneuter Versuch folgt.'));
      error.status = response.status;
      throw error;
    }
    return data;
  }

  /* ------------------------------------------------------------------ */
  /* Tabs and static wiring                                             */
  /* ------------------------------------------------------------------ */

  function showTab(name) {
    $$('.tab').forEach((tab) => {
      const active = tab.dataset.tab === name;
      tab.classList.toggle('active', active);
      tab.setAttribute('aria-selected', active ? 'true' : 'false');
    });
    $$('.tab-panel').forEach((panel) => {
      const active = panel.id === `tab-${name}`;
      panel.classList.toggle('active', active);
      panel.hidden = !active;
    });
    const tab = document.querySelector(`.tab[data-tab="${name}"]`);
    if (tab) $('page-heading').textContent = tab.textContent;
    if (name === 'offers' && state.csrf) loadOffers(state.offersPage).catch((error) => toast(error.message, 'bad'));
  }

  function wireTabs() {
    $$('.tab').forEach((tab) => {
      tab.addEventListener('click', () => showTab(tab.dataset.tab));
    });
  }

  /* ------------------------------------------------------------------ */
  /* Status, job card and events                                        */
  /* ------------------------------------------------------------------ */

  function statusClassForService(status) {
    if (!status) return '';
    if (status.setup_required) return '';
    return 'ok';
  }

  function updateFacts(status) {
    state.status = status;
    const version = status.version || '2.8.0';
    $('version-label').textContent = `v${version} · DSM`;
    $('service-dot').className = `dot ${statusClassForService(status)}`;
    $('service-label').textContent = status.setup_required ? t('Einrichtung erforderlich') : t('Dienst online');
    $('service-badge').textContent = status.setup_required ? t('Einrichtung') : t('Online');
    $('service-badge').className = `pill ${status.setup_required ? 'warn' : 'ok'}`;
    $('fact-uptime').textContent = formatDuration(status.uptime_seconds);
    const memory = status.memory || {};
    const worker = memory.worker || {};
    let memoryText = memory.rss_kb > 0
      ? `${memory.pss_kb > 0 ? formatBytes(memory.pss_kb * 1024) : '–'} PSS / ${formatBytes(memory.rss_kb * 1024)} RSS`
      : t('Nicht verfügbar');
    if (worker.rss_kb) {
      memoryText += ` · Worker ${formatBytes((worker.pss_kb || 0) * 1024)} PSS`;
    }
    $('fact-memory').textContent = memoryText;
    $('fact-output').textContent = status.output_dir || '–';
    $('fact-share').textContent = (status.share && status.share.root) || '–';
    $('fact-disk').textContent = status.disk
      ? t('{free} frei von {total}', { free: status.disk.free_text, total: status.disk.total_text })
      : '–';

    const session = status.session || {};
    const sessionPresent = Boolean(session.present);
    const sessionVerified = Boolean(session.verified);
    $('session-state').textContent = sessionPresent
      ? (sessionVerified ? t('Verbunden') : t('Importiert'))
      : t('Nicht eingerichtet');
    $('session-state').className = `pill ${sessionVerified ? 'ok' : 'warn'}`;
    $('session-user').textContent = session.user_id || '–';

    updateLibrary(status.library || {});
    updateScheduleLabels(status);
    renderRecentJobs(status.recent_jobs || []);
    const active = Boolean(status.active_job);
    for (const id of ['start-download', 'start-scan', 'load-subscriptions', 'test-session',
                      'scan-offers', 'renew-free', 'import-session', 'clear-session', 'save-library']) {
      $(id).disabled = active;
    }
  }

  function updateLibrary(library) {
    $('library-output').textContent = library.output_dir || '–';
    $('library-manifest').textContent = library.manifest ? t('vorhanden') : t('neu / leer');
    $('library-files').textContent = library.manifest ? String(library.files || 0) : '–';
    $('library-bytes').textContent = library.manifest ? formatBytes(library.bytes) : '–';
    $('library-writable').textContent = library.writable ? t('ja') : t('nein');
    $('library-error').textContent = library.error
      ? t('Das Manifest konnte nicht gelesen werden. Pfad und Berechtigungen prüfen.') : '';
    const disk = state.status && state.status.disk;
    $('library-disk').textContent = disk ? `${disk.free_text} ${t('frei')}` : '–';
  }

  function computeNextRun(enabled, time, lastRun) {
    if (!enabled) return '–';
    const match = /^([01][0-9]|2[0-3]):([0-5][0-9])$/.exec(String(time || ''));
    if (!match) return '–';
    const now = new Date();
    const candidate = new Date(now);
    candidate.setHours(Number(match[1]), Number(match[2]), 0, 0);
    const today = now.toISOString().slice(0, 10);
    if (candidate <= now || lastRun === today) candidate.setDate(candidate.getDate() + 1);
    return candidate.toLocaleString(locale(), {
      weekday: 'short', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
    });
  }

  function updateScheduleLabels(status) {
    const schedule = status.schedule || {};
    $('schedule-last').textContent = status.schedule_last_run || '–';
    $('schedule-next').textContent = computeNextRun(schedule.enabled, schedule.time, status.schedule_last_run);
  }

  function renderRecentJobs(jobs) {
    const body = $('recent-jobs');
    body.replaceChildren();
    if (!jobs.length) {
      const row = document.createElement('tr');
      const cell = document.createElement('td');
      cell.colSpan = 5;
      cell.className = 'muted';
      cell.textContent = t('Noch keine Aufträge.');
      row.appendChild(cell);
      body.appendChild(row);
      return;
    }
    for (const job of jobs) {
      const row = document.createElement('tr');
      const values = [
        `#${job.id}`,
        t(KIND_TEXT[job.kind] || job.kind),
        t(STATUS_TEXT[job.status] || job.status),
        jobSummary(job),
        formatDate(job.finished_at),
      ];
      values.forEach((value) => {
        const cell = document.createElement('td');
        cell.textContent = String(value);
        row.appendChild(cell);
      });
      body.appendChild(row);
    }
  }

  function jobSummary(job) {
    if (job.error) return job.error.slice(0, 100);
    const result = job.result || {};
    if (typeof result.downloaded === 'number') {
      return t('{n} neu · {e} vorhanden · {f} Fehler', {
        n: result.downloaded, e: result.existing || 0, f: result.errors || 0,
      });
    }
    if (typeof result.creators === 'number') return t('{n} Abonnements', { n: result.creators });
    if (result.message) return String(result.message).slice(0, 100);
    if (job.status === 'cancelled') return t('Abgebrochen');
    if (job.status === 'running' || job.status === 'queued') return job.phase || t('läuft');
    return '–';
  }

  function clearEvents() {
    state.lastEventId = 0;
    state.finishedJobId = null;
    state.eventsInitial = true;
    const list = $('event-list');
    list.replaceChildren();
    const item = document.createElement('li');
    item.className = 'muted';
    item.textContent = t('Noch keine Ereignisse in diesem Auftrag.');
    list.appendChild(item);
    $('event-count').textContent = '';
  }

  function appendEvents(events) {
    if (!events || !events.length) return;
    const list = $('event-list');
    const placeholder = list.querySelector('li.muted');
    if (placeholder && list.children.length === 1) list.replaceChildren();
    const nearBottom = list.scrollHeight - list.scrollTop - list.clientHeight < 40;
    for (const event of events) {
      if (Number(event.id) <= state.lastEventId) continue;
      state.lastEventId = Math.max(state.lastEventId, Number(event.id || 0));
      const item = document.createElement('li');
      item.className = event.level === 'media' ? 'media' : event.level;
      const time = document.createElement('span');
      time.className = 'event-time';
      time.textContent = formatTime(event.ts);
      const message = document.createElement('span');
      message.className = 'event-message';
      if (event.level === 'media') {
        try {
          const media = JSON.parse(event.message);
          message.textContent = `${media.profile || ''}: ${media.relative || ''} (${formatBytes(media.size)})`;
          if (media.relative && ['photo', 'gif', 'video'].includes(media.kind)) {
            const preview = document.createElement('button');
            preview.type = 'button';
            preview.className = 'ghost';
            preview.style.marginLeft = '8px';
            preview.textContent = t('Vorschau');
            preview.addEventListener('click', () => requestPreview(media.relative, media.kind));
            message.appendChild(preview);
          }
        } catch (_) {
          message.textContent = event.message;
        }
      } else {
        message.textContent = event.message;
      }
      item.append(time, message);
      list.appendChild(item);
      if (list.children.length > 250) list.removeChild(list.firstChild);
    }
    $('event-count').textContent = t('{n} Ereignisse', { n: list.children.length });
    if (nearBottom) list.scrollTop = list.scrollHeight;
  }

  function updateJobCard(job) {
    const empty = $('job-empty');
    const active = $('job-active');
    if (!job) {
      empty.hidden = false;
      active.hidden = true;
      $('job-status').textContent = t('Leerlauf');
      $('job-status').className = 'pill';
      return;
    }
    empty.hidden = true;
    active.hidden = false;
    $('job-status').textContent = t(STATUS_TEXT[job.status] || job.status);
    $('job-status').className = `pill ${statusClass(job.status)}`;
    if (job.status === 'completed' && Number(job.result?.errors) > 0) {
      $('job-status').textContent = t('Beendet mit Fehlern');
      $('job-status').className = 'pill warn';
    }
    $('job-title').textContent = `#${job.id} · ${t(KIND_TEXT[job.kind] || job.kind)}`;
    $('job-phase').textContent = job.phase || (ACTIVE.has(job.status) ? t('Wird vorbereitet …') : jobSummary(job));
    $('job-error').hidden = !job.error;
    $('job-error').textContent = job.error || '';

    const stats = job.stats || {};
    const number = (value) => Number.isFinite(Number(value)) ? Math.max(0, Number(value)) : 0;
    const done = number(job.progress_done ?? stats.overall_done);
    const total = number(job.progress_total ?? stats.overall_total);
    const running = ACTIVE.has(job.status);
    const scanning = job.kind === 'download' && stats.scanning !== false;
    const knownTotal = total > 0 && !scanning;
    let bar = 0;
    let progressText = '';
    if (job.status === 'completed') {
      bar = 100;
      progressText = t(job.request?.dry_run ? 'Scan abgeschlossen. Keine Medien heruntergeladen.' : 'Auftrag abgeschlossen.');
    } else if (knownTotal) {
      bar = Math.max(0, Math.min(100, (done / total) * 100));
      progressText = t(job.kind === 'download' ? '{done} / {total} Dateien verarbeitet' : '{done} / {total} Schritte', {
        done: done.toLocaleString(locale()), total: total.toLocaleString(locale()),
      });
    } else {
      progressText = running
        ? (job.kind === 'download'
          ? t('Suche läuft · {done} verarbeitet · bisher {total} gefunden', { done, total })
          : t('Auftrag läuft. Gesamtumfang noch unbekannt.'))
        : t(STATUS_TEXT[job.status] || job.status);
    }
    const progress = $('job-progress');
    progress.classList.toggle('indeterminate', running && !knownTotal);
    progress.classList.toggle('paused', job.pause_requested || job.status === 'paused');
    progress.classList.toggle('failed', job.status === 'failed');
    progress.setAttribute('aria-valuetext', progressText);
    if (knownTotal || job.status === 'completed') progress.setAttribute('aria-valuenow', String(Math.round(bar)));
    else progress.removeAttribute('aria-valuenow');
    $('job-progress-bar').style.width = `${bar}%`;
    $('job-progress-text').textContent = progressText;
    const currentTotal = number(stats.current_total);
    const current = number(stats.current_done);
    const speed = number(stats.current_speed);
    $('file-progress-section').hidden = !running || !stats.current_file;
    $('file-name').textContent = stats.current_file || '';
    $('file-progress').classList.toggle('indeterminate', currentTotal <= 0);
    const filePercent = currentTotal > 0 ? Math.min(100, 100 * current / currentTotal) : 0;
    $('file-progress-bar').style.width = `${filePercent}%`;
    if (currentTotal > 0) $('file-progress').setAttribute('aria-valuenow', String(Math.round(filePercent)));
    else $('file-progress').removeAttribute('aria-valuenow');
    $('file-progress-text').textContent = currentTotal > 0 ? `${formatBytes(current)} / ${formatBytes(currentTotal)}` : formatBytes(current);
    $('job-speed').textContent = running && speed > 0 ? `${formatBytes(speed)}/s` : '';
    const end = job.finished_at ? Date.parse(job.finished_at) : Date.now();
    const started = Date.parse(job.started_at || job.created_at);
    $('job-timing').textContent = Number.isFinite(started)
      ? `${t('Laufzeit')}: ${formatDuration((end - started) / 1000)}` : '';
    if (job.cancel_requested && running) $('job-phase').textContent = t('Abbruch angefordert. Worker wird beendet …');
    else if (job.pause_requested && running) $('job-phase').textContent = t('Pause angefordert. Warte auf sicheren Haltepunkt …');
    else if (running && stats.retry_at) {
      const seconds = Math.max(0, Math.ceil((Date.parse(stats.retry_at) - Date.now()) / 1000));
      $('job-phase').textContent = t('Temporärer API-/Netzwerkfehler. Neuer Leseversuch in {seconds} s. Abbruch bleibt möglich.', { seconds });
    } else if (running) {
      const activity = Date.parse(stats.last_activity_at || job.started_at || job.created_at);
      if (Number.isFinite(activity) && Date.now() - activity > 90000) {
        $('job-phase').textContent = t('Länger keine Fortschrittsmeldung. Warte auf Server oder Netzwerk; Sitzung und Verbindung prüfen.');
      }
    }

    const grid = $('job-stats');
    grid.replaceChildren();
    const items = [
      [t('Neu'), stats.downloaded || 0],
      [t('Vorhanden'), stats.existing || 0],
      [t('Geplant'), stats.planned || 0],
      [t('Fehler'), stats.errors || 0],
      [t('Gefiltert'), stats.filtered || 0],
      [t('Nicht verfügbar'), stats.unavailable || 0],
      ['DRM', stats.drm || 0],
      ['Streaming', stats.streaming || 0],
      [t('Übertragen'), stats.transferred_bytes ? formatBytes(stats.transferred_bytes) : '0 B'],
    ];
    if (job.kind === 'free_renew') items.splice(0, items.length,
      [t('Angemeldet'), stats.subscribed || job.result?.subscribed || 0],
      [t('Übersprungen'), stats.skipped || job.result?.skipped || 0],
      [t('Fehler'), stats.errors || job.result?.errors || 0]);
    if (!['download', 'free_renew'].includes(job.kind)) items.length = 0;
    for (const [label, value] of items) {
      const box = document.createElement('div');
      box.className = 'stat';
      const bold = document.createElement('b');
      bold.textContent = String(value);
      const span = document.createElement('span');
      span.textContent = label;
      box.append(bold, span);
      grid.appendChild(box);
    }

    const pause = $('job-pause');
    const cancel = $('job-cancel');
    const finished = !ACTIVE.has(job.status);
    pause.disabled = finished;
    cancel.disabled = finished;
    pause.textContent = job.pause_requested || job.status === 'paused' ? t('Fortsetzen') : t('Pause');
    cancel.disabled = finished || Boolean(job.cancel_requested);
  }

  function handleJobFinished(job) {
    if (!job || state.finishedJobId === job.id) return;
    state.finishedJobId = job.id;
    const result = job.result || {};
    if (job.kind === 'subscriptions' && job.status === 'completed') {
      loadCreators(1).catch(() => {});
      toast(t('{n} Abonnements geladen.', { n: result.creators || 0 }), 'ok');
    } else if (job.kind === 'test_session') {
      const box = $('session-result');
      box.className = `result-box ${job.status === 'completed' ? 'ok' : 'bad'}`;
      box.textContent = job.status === 'completed'
        ? (t(result.message || 'Sitzung akzeptiert.') + (result.username ? ` (@${result.username})` : ''))
        : t(job.error || 'Sitzungstest fehlgeschlagen.');
    } else if (job.kind === 'preview') {
      if (job.status === 'completed' && result.url && state.previewRequested) {
        window.open(result.url, '_blank', 'noopener');
      } else {
        toast(t(result.message || job.error || 'Vorschau nicht verfügbar.'), job.status === 'completed' ? '' : 'bad');
      }
      state.previewRequested = false;
    } else if (['offers_scan', 'free_renew'].includes(job.kind)) {
      loadOffers(1).catch(() => {});
      toast(t(job.status === 'completed' ? 'Auftrag abgeschlossen.' : (job.error || 'Auftrag fehlgeschlagen.')), job.status === 'completed' ? 'ok' : 'bad');
    } else if (job.kind === 'download') {
      if (job.status === 'completed') {
        toast(t('Download fertig: {n} neu, {e} vorhanden.', {
          n: result.downloaded || 0, e: result.existing || 0,
        }), 'ok');
      } else if (job.status === 'cancelled') {
        toast(t('Download abgebrochen. Fertige Dateien bleiben erhalten.'), '');
      } else {
        toast(t(job.error || 'Download fehlgeschlagen.'), 'bad');
      }
      $('library-output').textContent = state.status?.output_dir || '–';
    }
  }

  async function pollJob() {
    const selected = state.activeJob || state.lastJob;
    if (!selected) return;
    const jobId = selected.id;
    const data = await api(`/api/jobs/${jobId}?after=${state.lastEventId}${state.eventsInitial ? '&tail=1' : ''}`);
    if (!data.job || data.job.id !== jobId) throw new Error(t('Auftragsstatus konnte nicht aktualisiert werden.'));
    state.eventsInitial = false;
    appendEvents(data.events || []);
    state.lastJob = data.job;
    updateJobCard(data.job);
    if (!ACTIVE.has(data.job.status)) {
      state.activeJob = null;
      // Reloading a finished job must not re-run completion side effects.
      if (selected.status !== data.job.status || state.finishedJobId !== data.job.id) handleJobFinished(data.job);
    } else {
      state.activeJob = data.job;
    }
  }

  async function loadStatus() {
    const status = await api('/api/status');
    if (!Array.isArray(status.recent_jobs) || !status.version) throw new Error(t('Ungültige Serverantwort. Erneuter Versuch folgt.'));
    updateFacts(status);
    const previous = state.lastJob;
    const selected = status.active_job || status.recent_jobs[0] || null;
    if (selected && state.displayJobId !== selected.id) {
      state.displayJobId = selected.id;
      clearEvents();
      if (!status.active_job) state.finishedJobId = selected.id;
    }
    state.activeJob = status.active_job || null;
    state.lastJob = selected;
    updateJobCard(selected);
    if (previous && selected && previous.id === selected.id
        && ACTIVE.has(previous.status) && !ACTIVE.has(selected.status)) {
      state.needsJobPoll = true;
      handleJobFinished(selected);
    }
  }

  function connectionNotice(message = '', kind = 'warn') {
    const banner = $('connection-banner');
    banner.textContent = message;
    banner.className = `notice ${kind}`.trim();
    banner.hidden = !message;
  }

  function describeError(error) {
    if (!error) return t('Unbekannter Fehler');
    if (error.name === 'AbortError') return t('Zeitüberschreitung');
    const message = String(error.message || error).replace(/\s+/g, ' ').slice(0, 180);
    return error.status ? `HTTP ${error.status}: ${message}` : message;
  }

  function statusWarnings(status) {
    const warnings = Array.isArray(status && status.warnings) ? status.warnings : [];
    const detail = warnings
      .map((item) => `${item.section || '?'}${item.error ? ` (${item.error})` : ''}`)
      .join(', ');
    if (detail) {
      connectionNotice(t('Teilweise Statusfehler: {detail}. Letzter Stand bleibt sichtbar.', { detail }), 'warn');
    }
    return detail;
  }

  async function poll() {
    if (state.polling) return;
    state.polling = true;
    try {
      if (state.authExpired) return;
      if (!state.csrf) state.csrf = (await api('/api/session')).csrf;
      await loadStatus();
      state.failures = 0;
      state.lastSync = Date.now();
      $('last-sync').textContent = `${t('Aktualisiert')}: ${formatTime(new Date(state.lastSync).toISOString())}`;
      const setup = Boolean(state.status && state.status.setup_required);
      $('service-dot').className = `dot ${setup ? '' : 'ok'}`;
      $('service-label').textContent = setup ? t('Einrichtung erforderlich') : t('Dienst online');
      if (!statusWarnings(state.status)) connectionNotice();
      if (!state.settingsLoaded) {
        try { await loadSettings(); } catch (error) {
          connectionNotice(t('Dienst online. Einstellungen konnten nicht geladen werden: {detail}', {
            detail: describeError(error),
          }), 'warn');
        }
      }
      if (state.activeJob || state.eventsInitial || state.needsJobPoll) {
        try { await pollJob(); state.needsJobPoll = false; }
        catch (error) {
          if (error.status !== 401) {
            connectionNotice(t('Dienst online. Auftragsereignisse konnten nicht geladen werden: {detail}', {
              detail: describeError(error),
            }), 'warn');
          }
        }
      }
    } catch (error) {
      if (error.status === 401) return;
      state.failures += 1;
      if (state.failures >= 3) {
        $('service-dot').className = 'dot bad';
        $('service-label').textContent = `${t('Verbindung wird wiederhergestellt …')} (${describeError(error)})`;
      }
      connectionNotice(t('Statusaktualisierung fehlgeschlagen ({detail}). Letzter Stand bleibt sichtbar; laufende Aufträge werden dadurch nicht gestoppt.', {
        detail: describeError(error),
      }), state.failures >= 3 ? 'bad' : 'warn');
    } finally {
      state.polling = false;
    }
  }

  /* ------------------------------------------------------------------ */
  /* Settings and download form                                         */
  /* ------------------------------------------------------------------ */

  function outputDirValue() {
    return (state.settings && state.settings.output_dir) || '';
  }

  function collectDownloadOptions(dryRun = false) {
    const all = $('all-subscriptions').checked;
    const profiles = splitProfiles($('creator-names').value);
    if (!all) {
      for (const name of state.selectedCreators) {
        if (!profiles.includes(name)) profiles.push(name);
      }
    }
    return {
      output_dir: outputDirValue(),
      profiles: all ? [] : profiles,
      all_subscriptions: all,
      skip_profiles: [],
      categories: $$('[data-category]:checked').map((input) => input.dataset.category),
      types: {
        photos: $('type-photos').checked,
        videos: $('type-videos').checked,
        audio: $('type-audio').checked,
      },
      albums: $('opt-albums').checked,
      subfolders: $('opt-subfolders').checked,
      previews: $('opt-previews').checked,
      dry_run: Boolean(dryRun),
      since_days: Math.max(0, Math.min(36500, Number($('since-days').value) || 0)),
      rules_source: (state.settings && state.settings.rules_source) || '',
    };
  }

  function validateDownloadOptions(options) {
    if (!options.output_dir) throw new Error(t('Bitte einen Downloadordner auswählen.'));
    if (!options.all_subscriptions && options.profiles.length === 0) {
      throw new Error(t('Bitte Creator auswählen oder „Alle aktiven Abonnements“ aktivieren.'));
    }
    if (!options.categories.length) throw new Error(t('Mindestens eine Inhaltskategorie auswählen.'));
    if (!options.types.photos && !options.types.videos && !options.types.audio) {
      throw new Error(t('Mindestens einen Dateityp auswählen.'));
    }
  }

  function applyDownloadDefaults(defaults) {
    if (!defaults || !Object.keys(defaults).length) return;
    if (Array.isArray(defaults.profiles) && !$('creator-names').value) {
      $('creator-names').value = defaults.profiles.join(', ');
    }
    if (typeof defaults.all_subscriptions === 'boolean') $('all-subscriptions').checked = defaults.all_subscriptions;
    if (Array.isArray(defaults.categories) && defaults.categories.length) {
      $$('[data-category]').forEach((input) => {
        input.checked = defaults.categories.includes(input.dataset.category);
      });
    }
    if (defaults.types) {
      $('type-photos').checked = Boolean(defaults.types.photos);
      $('type-videos').checked = Boolean(defaults.types.videos);
      $('type-audio').checked = Boolean(defaults.types.audio);
    }
    if (typeof defaults.albums === 'boolean') $('opt-albums').checked = defaults.albums;
    if (typeof defaults.subfolders === 'boolean') $('opt-subfolders').checked = defaults.subfolders;
    if (typeof defaults.previews === 'boolean') $('opt-previews').checked = defaults.previews;
    if (Number.isFinite(Number(defaults.since_days))) $('since-days').value = Number(defaults.since_days);
    updateCreatorSelection();
  }

  async function loadSettings() {
    const settings = await api('/api/settings');
    state.settings = settings;
    applyLibraryPath(settings);
    const schedule = settings.schedule || {};
    $('schedule-enabled').checked = Boolean(schedule.enabled);
    $('schedule-time').value = schedule.time || '03:30';
    $('schedule-last').textContent = settings.schedule_last_run || '–';
    if (settings.proxy_set) {
      $('proxy').value = '';
      $('proxy').placeholder = t('Gesetzt: {proxy} – leer lassen zum Behalten', { proxy: settings.proxy });
    } else {
      $('proxy').value = '';
      $('proxy').placeholder = 'http://192.168.1.10:8080';
    }
    $('rules-source').value = settings.rules_source || '';
    $('about-version').textContent = settings.version || '–';
    $('about-package').textContent = settings.package_version || '–';
    applyDownloadDefaults(settings.download_defaults || {});
    state.settingsLoaded = true;
    updateCreatorSelection();
    loadCreators(1).catch(() => {});
    const renewal = settings.free_renewal || {};
    $('renewal-profiles').value = (renewal.profiles || []).join(', ');
    $('renewal-enabled').checked = Boolean(renewal.enabled);
    $('renewal-time').value = renewal.time || '04:00';
    $('renewal-consent').checked = false;
    $('renewal-summary').textContent = t(renewal.enabled ? 'Automatik aktiv – nur gespeicherte kostenlose Profile.' : 'Automatik deaktiviert.');
  }

  function applyLibraryPath(settings) {
    $('output-dir').value = settings.output_dir || '';
    $('library-dir').value = settings.output_dir || '';
    $('storage-setup').hidden = Boolean(settings.output_dir);
  }

  async function saveLibraryPath() {
    const path = $('library-dir').value.trim();
    if (!path) { toast(t('Bitte einen Downloadordner auswählen.'), 'bad'); return; }
    const button = $('save-library');
    setBusy(button, true, t('Speichern …'));
    try {
      state.settings = await api('/api/settings', { method: 'POST', body: { output_dir: path } });
      applyLibraryPath(state.settings);
      await poll();
      toast(t('Bibliothekspfad gespeichert. Dateien wurden nicht verschoben.'), 'ok');
    } catch (error) {
      toast(error.message, 'bad');
    } finally {
      setBusy(button, false);
    }
  }

  /* ------------------------------------------------------------------ */
  /* Creators                                                           */
  /* ------------------------------------------------------------------ */

  function updateCreatorSelection() {
    const names = new Set(splitProfiles($('creator-names').value));
    for (const name of state.selectedCreators) names.add(name);
    $('creator-selection').textContent = $('all-subscriptions').checked
      ? t('Alle Abonnements')
      : t('{n} ausgewählt', { n: names.size });
  }

  async function loadCreators(page = 1) {
    const requestId = ++state.creatorRequest;
    state.creatorQuery = $('creator-search').value.trim();
    const query = encodeURIComponent(state.creatorQuery);
    const data = await api(`/api/creators?page=${page}&q=${query}&per_page=50`);
    if (requestId !== state.creatorRequest) return;
    state.creatorPage = data.page || 1;
    state.creatorPages = data.pages || 1;
    state.creatorTotal = data.total || 0;
    const list = $('creator-list');
    list.replaceChildren();
    if (!data.items || !data.items.length) {
      const note = document.createElement('p');
      note.className = 'muted';
      note.textContent = state.creatorQuery
        ? t('Keine Treffer.')
        : t('Keine Abonnements gespeichert. „Abonnements laden“ startet einen kurzen Auftrag.');
      list.appendChild(note);
    } else {
      for (const creator of data.items) {
        const label = document.createElement('label');
        label.className = 'creator-item';
        const input = document.createElement('input');
        input.type = 'checkbox';
        input.checked = state.selectedCreators.has(creator.username);
        input.addEventListener('change', () => {
          if (input.checked) state.selectedCreators.add(creator.username);
          else state.selectedCreators.delete(creator.username);
          updateCreatorSelection();
        });
        const name = document.createElement('span');
        name.textContent = creator.display_name || creator.username;
        const handle = document.createElement('small');
        handle.textContent = `@${creator.username}`;
        label.append(input, name, handle);
        list.appendChild(label);
      }
    }
    $('creator-page').textContent = t('Seite {page} / {pages} · {total}', {
      page: state.creatorPage, pages: state.creatorPages, total: state.creatorTotal,
    });
    $('creator-prev').disabled = state.creatorPage <= 1;
    $('creator-next').disabled = state.creatorPage >= state.creatorPages;
  }

  /* ------------------------------------------------------------------ */
  /* Folder picker                                                      */
  /* ------------------------------------------------------------------ */

  async function openFolderPicker(startPath) {
    $('folder-modal').hidden = false;
    $('new-folder-name').value = '';
    await loadFolder(startPath || outputDirValue());
  }

  function closeFolderPicker() {
    $('folder-modal').hidden = true;
  }

  async function loadFolder(path) {
    const requestId = ++state.folderRequest;
    $('folder-select').disabled = true;
    const data = await api(`/api/folders?path=${encodeURIComponent(path || '')}`);
    if (requestId !== state.folderRequest) return;
    state.folderPath = data.path;
    state.folderParent = data.parent;
    state.folderRoot = data.root;
    $('folder-select').disabled = false;
    $('folder-path').textContent = data.path;
    $('folder-up').disabled = !data.parent;
    const roots = $('folder-roots');
    roots.replaceChildren();
    for (const root of data.roots || []) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'ghost';
      button.textContent = root;
      button.addEventListener('click', () => loadFolder(root).catch((error) => toast(error.message, 'bad')));
      roots.appendChild(button);
    }
    const list = $('folder-list');
    list.replaceChildren();
    if (!data.items || !data.items.length) {
      const note = document.createElement('p');
      note.className = 'muted';
      note.textContent = t('Keine Unterordner.');
      list.appendChild(note);
    } else {
      for (const item of data.items) {
        const row = document.createElement('div');
        row.className = 'folder-item';
        const icon = document.createElement('span');
        icon.textContent = '📁';
        icon.setAttribute('aria-hidden', 'true');
        const name = document.createElement('span');
        name.textContent = item.name;
        row.append(icon, name);
        row.addEventListener('click', () => loadFolder(item.path).catch((error) => toast(error.message, 'bad')));
        list.appendChild(row);
      }
    }
  }

  async function createFolder() {
    const name = $('new-folder-name').value.trim();
    if (!name) { toast(t('Bitte einen Ordnernamen eingeben.'), 'bad'); return; }
    if (!window.confirm(t('Neuen Unterordner anlegen: {path}?', { path: `${state.folderPath}/${name}` }))) return;
    const button = $('create-folder');
    setBusy(button, true, t('Anlegen …'));
    try {
      const data = await api('/api/folders', {
        method: 'POST',
        body: { parent: state.folderPath, name },
      });
      $('new-folder-name').value = '';
      await loadFolder(data.path);
      toast(t('Ordner angelegt.'), 'ok');
    } catch (error) {
      toast(error.message, 'bad');
    } finally {
      setBusy(button, false);
    }
  }

  /* ------------------------------------------------------------------ */
  /* Actions                                                            */
  /* ------------------------------------------------------------------ */

  async function startJob(kind, options = {}, message = '') {
    const data = await api('/api/jobs', { method: 'POST', body: { kind, options } });
    if (data.job) {
      state.activeJob = data.job;
      state.lastJob = data.job;
      clearEvents();
      updateJobCard(data.job);
      showTab('dashboard');
      if (message) toast(message, 'ok');
      await poll();
    }
    return data.job;
  }

  async function startDownload(dryRun) {
    const options = collectDownloadOptions(dryRun);
    try {
      validateDownloadOptions(options);
    } catch (error) {
      $('download-message').textContent = error.message;
      toast(error.message, 'bad');
      return;
    }
    const button = dryRun ? $('start-scan') : $('start-download');
    setBusy(button, true, dryRun ? t('Scan läuft …') : t('Startet …'));
    try {
      $('download-message').textContent = '';
      await startJob('download', options, dryRun ? t('Scan gestartet.') : t('Download gestartet.'));
    } catch (error) {
      toast(error.message, 'bad');
    } finally {
      setBusy(button, false);
    }
  }

  async function saveDefaults() {
    const options = collectDownloadOptions(false);
    const button = $('save-defaults');
    setBusy(button, true, t('Speichern …'));
    try {
      await api('/api/settings', { method: 'POST', body: { download_defaults: options } });
      toast(t('Download-Einstellungen gespeichert.'), 'ok');
    } catch (error) {
      toast(error.message, 'bad');
    } finally {
      setBusy(button, false);
    }
  }

  async function importSession() {
    const text = $('session-text').value;
    if (!text.trim()) { toast(t('Bitte eine Sitzung einfügen.'), 'bad'); return; }
    const button = $('import-session');
    setBusy(button, true, t('Importiere …'));
    try {
      const data = await api('/api/session/import', { method: 'POST', body: { text } });
      $('session-text').value = '';
      toast(t('Sitzung importiert (Konto-ID {id}). Bitte jetzt testen.', { id: data.user_id }), 'ok');
      await poll();
    } catch (error) {
      toast(error.message, 'bad');
    } finally {
      setBusy(button, false);
    }
  }

  async function readSessionFile(event) {
    const file = event.target.files[0];
    if (!file) return;
    try {
      if (file.size > 1900000) throw new Error(t('Importdatei ist zu groß (max. 1,9 MB).'));
      $('session-text').value = await file.text();
      toast(t('Datei geladen. Erst Importieren überträgt die Sitzung zum NAS.'));
    } catch (error) {
      toast(error.message, 'bad');
    } finally {
      event.target.value = '';
    }
  }

  async function testSession() {
    const button = $('test-session');
    setBusy(button, true, t('Prüfe …'));
    $('session-result').className = 'result-box';
    $('session-result').textContent = t('Sitzung wird geprüft …');
    try {
      await startJob('test_session', {}, t('Sitzungstest gestartet.'));
    } catch (error) {
      $('session-result').className = 'result-box bad';
      $('session-result').textContent = error.message;
      toast(error.message, 'bad');
    } finally {
      setBusy(button, false);
    }
  }

  async function clearSession() {
    if (!window.confirm(t('Sitzung wirklich vom NAS löschen?'))) return;
    try {
      await api('/api/session/clear', { method: 'POST', body: {} });
      toast(t('Sitzung gelöscht.'), 'ok');
      await poll();
    } catch (error) {
      toast(error.message, 'bad');
    }
  }

  async function saveProxy(clear = false) {
    const value = clear ? '' : $('proxy').value.trim();
    if (!clear && !value && state.settings && state.settings.proxy_set) {
      toast(t('Proxy unverändert. Zum Entfernen „Entfernen“ wählen.'));
      return;
    }
    try {
      const data = await api('/api/settings', { method: 'POST', body: { proxy: value } });
      state.settings = { ...(state.settings || {}), ...data };
      if (data.proxy_set) {
        $('proxy').value = '';
        $('proxy').placeholder = t('Gesetzt: {proxy} – leer lassen zum Behalten', { proxy: data.proxy });
      } else {
        $('proxy').value = '';
        $('proxy').placeholder = 'http://192.168.1.10:8080';
      }
      toast(clear ? t('Proxy entfernt.') : t('Proxy gespeichert.'), 'ok');
    } catch (error) {
      toast(error.message, 'bad');
    }
  }

  async function saveRules() {
    try {
      const data = await api('/api/settings', {
        method: 'POST',
        body: { rules_source: $('rules-source').value.trim() },
      });
      state.settings = { ...(state.settings || {}), ...data };
      toast(t('Regelquelle gespeichert.'), 'ok');
    } catch (error) {
      toast(error.message, 'bad');
    }
  }

  async function saveSchedule() {
    const options = collectDownloadOptions(false);
    if ($('schedule-enabled').checked) {
      try {
        validateDownloadOptions(options);
      } catch (error) {
        toast(error.message, 'bad');
        return;
      }
    }
    const schedule = {
      enabled: $('schedule-enabled').checked,
      time: $('schedule-time').value || '03:30',
      options,
    };
    const button = $('save-schedule');
    setBusy(button, true, t('Speichern …'));
    try {
      const data = await api('/api/settings', { method: 'POST', body: { schedule } });
      state.settings = { ...(state.settings || {}), ...data };
      toast(t('Zeitplan gespeichert.'), 'ok');
      await poll();
    } catch (error) {
      toast(error.message, 'bad');
    } finally {
      setBusy(button, false);
    }
  }

  async function requestPreview(relative, kind) {
    try {
      state.previewRequested = true;
      await startJob('preview', {
        path: relative,
        kind,
        output_dir: (state.lastJob && state.lastJob.request && state.lastJob.request.output_dir) || outputDirValue(),
      }, t('Vorschau wird erzeugt …'));
    } catch (error) {
      state.previewRequested = false;
      toast(error.message, 'bad');
    }
  }

  async function loadOffers(page = 1) {
    const data = await api(`/api/offers?page=${page}`);
    state.offersPage = data.page;
    $('offers-list').replaceChildren();
    for (const item of data.items || []) {
      const row = document.createElement('tr');
      for (const value of [item.username, item.kind === 'free' ? t('Dauerhaft kostenlos') : t('Trial – Website prüfen'), item.status, item.detail]) {
        const cell = document.createElement('td');
        cell.textContent = value;
        row.appendChild(cell);
      }
      const cell = document.createElement('td');
      const link = document.createElement('a');
      link.href = `https://onlyfans.com/${encodeURIComponent(item.username)}`;
      link.target = '_blank'; link.rel = 'noopener noreferrer'; link.textContent = t('Öffnen');
      cell.appendChild(link); row.appendChild(cell); $('offers-list').appendChild(row);
    }
    if (!data.items?.length) {
      const row = document.createElement('tr'); const cell = document.createElement('td');
      cell.colSpan = 5; cell.textContent = t('Noch keine Angebote. Suche starten.'); row.appendChild(cell); $('offers-list').appendChild(row);
    }
    $('offers-page').textContent = `${data.page} / ${data.pages} · ${data.total}`;
    $('offers-prev').disabled = data.page <= 1;
    $('offers-next').disabled = data.page >= data.pages;
  }

  function renewalOptions() {
    return { profiles: splitProfiles($('renewal-profiles').value), confirm_free_only: $('renewal-consent').checked,
      enabled: $('renewal-enabled').checked, time: $('renewal-time').value || '04:00' };
  }

  async function renewalAction(action) {
    try {
      const options = renewalOptions();
      if (action !== 'scan' && (action === 'run' || options.enabled)) {
        if (!options.confirm_free_only || !options.profiles.length) throw new Error(t('Bitte Profile auswählen und kostenlose Wiederanmeldung bestätigen.'));
        if (!window.confirm(t('Nur ausgewählte dauerhaft kostenlose Profile anmelden? Trials und kostenpflichtige Profile werden übersprungen.'))) return;
      }
      if (action === 'save') {
        const settings = await api('/api/settings', { method: 'POST', body: { free_renewal: options } });
        state.settings = settings;
        $('renewal-summary').textContent = t(options.enabled ? 'Automatik aktiv – nur gespeicherte kostenlose Profile.' : 'Automatik deaktiviert.');
        toast(t('Einstellungen gespeichert.'), 'ok');
      } else {
        await startJob(action === 'scan' ? 'offers_scan' : 'free_renew', options);
      }
    } catch (error) { toast(error.message, 'bad'); }
  }

  /* ------------------------------------------------------------------ */
  /* Initialisation                                                     */
  /* ------------------------------------------------------------------ */

  function wireEvents() {
    $('scan-offers').addEventListener('click', () => renewalAction('scan'));
    $('renew-free').addEventListener('click', () => renewalAction('run'));
    $('save-renewal').addEventListener('click', () => renewalAction('save'));
    $('refresh-offers').addEventListener('click', () => loadOffers(state.offersPage).catch((error) => toast(error.message, 'bad')));
    $('offers-prev').addEventListener('click', () => loadOffers(state.offersPage - 1).catch((error) => toast(error.message, 'bad')));
    $('offers-next').addEventListener('click', () => loadOffers(state.offersPage + 1).catch((error) => toast(error.message, 'bad')));
    $('refresh-button').addEventListener('click', () => poll());
    $('logout-button').addEventListener('click', async () => {
      try { await api('/api/logout', { method: 'POST', body: {} }); } catch (_) { /* ignore */ }
      window.location.replace('/login');
    });

    $('browse-folder').addEventListener('click', () => showTab('settings'));
    $('setup-storage').addEventListener('click', () => showTab('settings'));
    $('browse-library').addEventListener('click', () => {
      openFolderPicker($('library-dir').value.trim()).catch((error) => toast(error.message, 'bad'));
    });
    $('save-library').addEventListener('click', saveLibraryPath);

    $('load-subscriptions').addEventListener('click', async () => {
      const button = $('load-subscriptions');
      setBusy(button, true, t('Lade …'));
      try {
        await startJob('subscriptions', {}, t('Abonnements werden geladen.'));
      } catch (error) {
        toast(error.message, 'bad');
      } finally {
        setBusy(button, false);
      }
    });
    $('clear-creators').addEventListener('click', () => {
      state.selectedCreators.clear();
      $('creator-names').value = '';
      $$('#creator-list input[type="checkbox"]').forEach((input) => { input.checked = false; });
      updateCreatorSelection();
    });
    $('all-subscriptions').addEventListener('change', updateCreatorSelection);
    $('creator-names').addEventListener('input', updateCreatorSelection);
    let searchTimer = null;
    $('creator-search').addEventListener('input', () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => {
        state.creatorQuery = $('creator-search').value.trim();
        loadCreators(1).catch((error) => toast(error.message, 'bad'));
      }, 300);
    });
    $('creator-prev').addEventListener('click', () => loadCreators(state.creatorPage - 1));
    $('creator-next').addEventListener('click', () => loadCreators(state.creatorPage + 1));

    $('download-form').addEventListener('submit', (event) => {
      event.preventDefault();
      startDownload(false);
    });
    $('start-scan').addEventListener('click', () => startDownload(true));
    $('save-defaults').addEventListener('click', saveDefaults);

    $('import-session').addEventListener('click', importSession);
    $('session-file').addEventListener('change', readSessionFile);
    $('test-session').addEventListener('click', testSession);
    $('clear-session').addEventListener('click', clearSession);
    $('save-proxy').addEventListener('click', () => saveProxy(false));
    $('clear-proxy').addEventListener('click', () => saveProxy(true));
    $('save-rules').addEventListener('click', saveRules);
    $('save-schedule').addEventListener('click', saveSchedule);

    $('password-form').addEventListener('submit', async (event) => {
      event.preventDefault();
      const current = $('current-password').value;
      const next = $('new-password').value;
      const confirm = $('confirm-password').value;
      if (next !== confirm) { toast(t('Die neuen Passwörter stimmen nicht überein.'), 'bad'); return; }
      const button = event.submitter;
      setBusy(button, true, t('Ändere …'));
      try {
        await api('/api/password', {
          method: 'POST',
          body: { current, new: next, confirm },
        });
        $('current-password').value = '';
        $('new-password').value = '';
        $('confirm-password').value = '';
        toast(t('Passwort geändert.'), 'ok');
      } catch (error) {
        toast(error.message, 'bad');
      } finally {
        setBusy(button, false);
      }
    });

    $('folder-close').addEventListener('click', closeFolderPicker);
    $('folder-select').addEventListener('click', () => {
      $('library-dir').value = state.folderPath;
      closeFolderPicker();
    });
    $('folder-up').addEventListener('click', () => {
      if (state.folderParent) loadFolder(state.folderParent).catch((error) => toast(error.message, 'bad'));
    });
    $('create-folder').addEventListener('click', createFolder);
    $('folder-modal').addEventListener('click', (event) => {
      if (event.target === $('folder-modal')) closeFolderPicker();
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') closeFolderPicker();
    });

    $('job-pause').addEventListener('click', async () => {
      if (!state.activeJob) return;
      const paused = state.activeJob.pause_requested || state.activeJob.status === 'paused';
      try {
        await api(`/api/jobs/${state.activeJob.id}/${paused ? 'resume' : 'pause'}`, {
          method: 'POST', body: {},
        });
        toast(paused ? t('Auftrag fortgesetzt.') : t('Auftrag pausiert.'));
        await poll();
      } catch (error) {
        toast(error.message, 'bad');
      }
    });
    $('job-cancel').addEventListener('click', async () => {
      if (!state.activeJob) return;
      if (!window.confirm(t('Auftrag wirklich abbrechen? Fertige Dateien bleiben erhalten.'))) return;
      try {
        await api(`/api/jobs/${state.activeJob.id}/cancel`, { method: 'POST', body: {} });
        toast(t('Abbruch angefordert.'));
        await poll();
      } catch (error) {
        toast(error.message, 'bad');
      }
    });

    $('refresh-library').addEventListener('click', () => poll());
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) poll();
    });
    document.addEventListener('ofdl-language', () => {
      if (state.status) updateFacts(state.status);
      updateJobCard(state.activeJob || state.lastJob);
      updateCreatorSelection();
      if (state.creatorTotal) loadCreators(state.creatorPage).catch(() => {});
      const activeTab = document.querySelector('.tab.active');
      if (activeTab) $('page-heading').textContent = activeTab.textContent;
    });
  }

  async function boot() {
    await window.ofdlI18n?.ready;
    // Install retry before the first request. A failed boot must not strand UI.
    window.setInterval(() => { if (!document.hidden) poll(); }, 3000);
    await poll();
    if (state.settingsLoaded && !outputDirValue() && !state.activeJob) showTab('settings');
  }

  wireTabs();
  wireEvents();
  boot();
})();
