/* OnlyFans DL DSM UI. No external dependencies; all data stays on the NAS. */
(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const ACTIVE = new Set(['queued', 'running', 'paused']);
  const STATUS_TEXT = {
    queued: 'Wartet', running: 'Läuft', paused: 'Pausiert',
    completed: 'Fertig', failed: 'Fehler', cancelled: 'Abgebrochen',
  };
  const KIND_TEXT = {
    test_session: 'Sitzungstest', subscriptions: 'Abonnements',
    download: 'Download', preview: 'Vorschau',
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
    return date.toLocaleString('de-DE', {
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit',
    });
  }

  function formatTime(value) {
    if (!value) return '–';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
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
    const init = {
      credentials: 'same-origin',
      headers: { Accept: 'application/json', ...(options.headers || {}) },
      ...options,
    };
    if (state.csrf) init.headers['X-CSRF-Token'] = state.csrf;
    if (init.body && typeof init.body !== 'string') {
      init.headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(init.body);
    }
    const response = await fetch(path, init);
    let data = null;
    const type = response.headers.get('Content-Type') || '';
    if (type.includes('application/json')) {
      try { data = await response.json(); } catch (_) { data = null; }
    }
    if (response.status === 401) {
      window.location.replace('/login');
      throw new Error('Anmeldung erforderlich.');
    }
    if (!response.ok) {
      const message = (data && data.error) || `HTTP ${response.status}`;
      const error = new Error(message);
      error.status = response.status;
      error.data = data;
      throw error;
    }
    return data || {};
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
    $('service-label').textContent = status.setup_required ? 'Einrichtung erforderlich' : 'Dienst online';
    $('service-badge').textContent = status.setup_required ? 'Einrichtung' : 'Online';
    $('service-badge').className = `pill ${status.setup_required ? 'warn' : 'ok'}`;
    $('fact-uptime').textContent = formatDuration(status.uptime_seconds);
    const memory = status.memory || {};
    const worker = memory.worker || {};
    let memoryText = `${formatBytes((memory.pss_kb || 0) * 1024)} PSS / ${formatBytes((memory.rss_kb || 0) * 1024)} RSS`;
    if (worker.rss_kb) {
      memoryText += ` · Worker ${formatBytes((worker.pss_kb || 0) * 1024)} PSS`;
    }
    $('fact-memory').textContent = memoryText;
    $('fact-output').textContent = status.output_dir || '–';
    $('fact-share').textContent = (status.share && status.share.root) || '–';
    $('fact-disk').textContent = status.disk
      ? `${status.disk.free_text} frei von ${status.disk.total_text}`
      : '–';

    const session = status.session || {};
    const sessionPresent = Boolean(session.present);
    const sessionVerified = Boolean(session.verified);
    $('session-state').textContent = sessionPresent
      ? (sessionVerified ? 'Verbunden' : 'Importiert')
      : 'Nicht eingerichtet';
    $('session-state').className = `pill ${sessionVerified ? 'ok' : 'warn'}`;
    $('session-user').textContent = session.user_id || '–';

    updateLibrary(status.library || {});
    updateScheduleLabels(status);
    renderRecentJobs(status.recent_jobs || []);
  }

  function updateLibrary(library) {
    $('library-output').textContent = library.output_dir || '–';
    $('library-manifest').textContent = library.manifest ? 'vorhanden' : 'neu / leer';
    $('library-files').textContent = library.manifest ? String(library.files || 0) : '–';
    $('library-bytes').textContent = library.manifest ? formatBytes(library.bytes) : '–';
    $('library-writable').textContent = library.writable ? 'ja' : 'nein';
    const disk = state.status && state.status.disk;
    $('library-disk').textContent = disk ? `${disk.free_text} frei` : '–';
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
    return candidate.toLocaleString('de-DE', {
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
      cell.textContent = 'Noch keine Aufträge.';
      row.appendChild(cell);
      body.appendChild(row);
      return;
    }
    for (const job of jobs) {
      const row = document.createElement('tr');
      const values = [
        `#${job.id}`,
        KIND_TEXT[job.kind] || job.kind,
        STATUS_TEXT[job.status] || job.status,
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
      return `${result.downloaded} neu · ${result.existing || 0} vorhanden · ${result.errors || 0} Fehler`;
    }
    if (typeof result.creators === 'number') return `${result.creators} Abonnements`;
    if (result.message) return String(result.message).slice(0, 100);
    if (job.status === 'cancelled') return 'Abgebrochen';
    if (job.status === 'running' || job.status === 'queued') return job.phase || 'läuft';
    return '–';
  }

  function clearEvents() {
    state.lastEventId = 0;
    state.finishedJobId = null;
    const list = $('event-list');
    list.replaceChildren();
    const item = document.createElement('li');
    item.className = 'muted';
    item.textContent = 'Noch keine Ereignisse in diesem Auftrag.';
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
            preview.textContent = 'Vorschau';
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
    $('event-count').textContent = `${list.children.length} Ereignisse`;
    if (nearBottom) list.scrollTop = list.scrollHeight;
  }

  function updateJobCard(job) {
    const empty = $('job-empty');
    const active = $('job-active');
    if (!job) {
      empty.hidden = false;
      active.hidden = true;
      $('job-status').textContent = 'Leerlauf';
      $('job-status').className = 'pill';
      return;
    }
    empty.hidden = true;
    active.hidden = false;
    $('job-status').textContent = STATUS_TEXT[job.status] || job.status;
    $('job-status').className = `pill ${statusClass(job.status)}`;
    $('job-title').textContent = `#${job.id} · ${KIND_TEXT[job.kind] || job.kind}`;
    $('job-phase').textContent = job.phase || (ACTIVE.has(job.status) ? 'Wird vorbereitet …' : jobSummary(job));

    const stats = job.stats || {};
    let done = Number(job.progress_done || stats.overall_done || 0);
    let total = Number(job.progress_total || stats.overall_total || 0);
    let bar = 0;
    let progressText = '';
    if (total > 0) {
      bar = Math.max(0, Math.min(100, (done / total) * 100));
      progressText = `${done.toLocaleString('de-DE')} / ${total.toLocaleString('de-DE')} Dateien`;
    } else if (Number(stats.current_total) > 0) {
      const current = Number(stats.current_done || 0);
      const currentTotal = Number(stats.current_total || 0);
      bar = Math.max(0, Math.min(100, (current / currentTotal) * 100));
      progressText = `${formatBytes(current)} / ${formatBytes(currentTotal)}`;
    } else {
      progressText = ACTIVE.has(job.status) ? 'Ermittlung läuft …' : 'Keine Fortschrittsdaten';
    }
    $('job-progress-bar').style.width = `${bar}%`;
    $('job-progress-text').textContent = progressText;
    $('job-speed').textContent = stats.current_speed
      ? `${formatBytes(stats.current_speed)}/s · ${stats.current_file || ''}`
      : '';

    const grid = $('job-stats');
    grid.replaceChildren();
    const items = [
      ['Neu', stats.downloaded || 0],
      ['Vorhanden', stats.existing || 0],
      ['Geplant', stats.planned || 0],
      ['Fehler', stats.errors || 0],
      ['Gefiltert', stats.filtered || 0],
      ['Nicht verfügbar', stats.unavailable || 0],
      ['DRM', stats.drm || 0],
      ['Streaming', stats.streaming || 0],
      ['Übertragen', stats.transferred_bytes ? formatBytes(stats.transferred_bytes) : '0 B'],
    ];
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
    pause.textContent = job.status === 'paused' ? 'Fortsetzen' : 'Pause';
  }

  function handleJobFinished(job) {
    if (!job || state.finishedJobId === job.id) return;
    state.finishedJobId = job.id;
    const result = job.result || {};
    if (job.kind === 'subscriptions' && job.status === 'completed') {
      loadCreators(1).catch(() => {});
      toast(`${result.creators || 0} Abonnements geladen.`, 'ok');
    } else if (job.kind === 'test_session') {
      const box = $('session-result');
      box.className = `result-box ${job.status === 'completed' ? 'ok' : 'bad'}`;
      box.textContent = job.status === 'completed'
        ? (result.message || 'Sitzung akzeptiert.') + (result.username ? ` (@${result.username})` : '')
        : (job.error || 'Sitzungstest fehlgeschlagen.');
      loadStatus().catch(() => {});
    } else if (job.kind === 'preview') {
      if (job.status === 'completed' && result.url) {
        window.open(result.url, '_blank', 'noopener');
      } else {
        toast(result.message || job.error || 'Vorschau nicht verfügbar.', job.status === 'completed' ? '' : 'bad');
      }
    } else if (job.kind === 'download') {
      if (job.status === 'completed') {
        toast(`Download fertig: ${result.downloaded || 0} neu, ${result.existing || 0} vorhanden.`, 'ok');
      } else if (job.status === 'cancelled') {
        toast('Download abgebrochen. Fertige Dateien bleiben erhalten.', '');
      } else {
        toast(job.error || 'Download fehlgeschlagen.', 'bad');
      }
      $('library-output').textContent = state.status?.output_dir || '–';
      loadStatus().catch(() => {});
    }
  }

  async function pollJob() {
    if (!state.activeJob) return;
    const jobId = state.activeJob.id;
    const data = await api(`/api/jobs/${jobId}?after=${state.lastEventId}`);
    appendEvents(data.events || []);
    state.lastJob = data.job;
    updateJobCard(data.job);
    if (!ACTIVE.has(data.job.status)) {
      state.activeJob = null;
      handleJobFinished(data.job);
    } else {
      state.activeJob = data.job;
    }
  }

  async function loadStatus() {
    const status = await api('/api/status');
    updateFacts(status);
    const active = status.active_job;
    if (active) {
      if (!state.activeJob || state.activeJob.id !== active.id) {
        state.lastEventId = 0;
        state.finishedJobId = null;
        clearEvents();
      }
      state.activeJob = active;
      state.lastJob = active;
      updateJobCard(active);
    } else if (state.activeJob) {
      // Poll once more so the final state and events are captured.
      await pollJob();
      state.activeJob = null;
    } else if (state.lastJob) {
      updateJobCard(state.lastJob);
    } else {
      updateJobCard(null);
    }
  }

  async function poll() {
    if (state.polling) return;
    state.polling = true;
    try {
      await loadStatus();
      if (state.activeJob) await pollJob();
    } catch (error) {
      $('service-dot').className = 'dot bad';
      $('service-label').textContent = 'Dienst nicht erreichbar';
    } finally {
      state.polling = false;
    }
  }

  /* ------------------------------------------------------------------ */
  /* Settings and download form                                         */
  /* ------------------------------------------------------------------ */

  function outputDirValue() {
    return $('output-dir').value.trim();
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
    if (!options.output_dir) throw new Error('Bitte einen Downloadordner auswählen.');
    if (!options.all_subscriptions && options.profiles.length === 0) {
      throw new Error('Bitte Creator auswählen oder „Alle aktiven Abonnements“ aktivieren.');
    }
    if (!options.categories.length) throw new Error('Mindestens eine Inhaltskategorie auswählen.');
    if (!options.types.photos && !options.types.videos && !options.types.audio) {
      throw new Error('Mindestens einen Dateityp auswählen.');
    }
  }

  function applyDownloadDefaults(defaults) {
    if (!defaults || !Object.keys(defaults).length) return;
    if (!$('output-dir').value && defaults.output_dir) $('output-dir').value = defaults.output_dir;
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
    if (!$('output-dir').value) $('output-dir').value = settings.output_dir || '';
    const schedule = settings.schedule || {};
    $('schedule-enabled').checked = Boolean(schedule.enabled);
    $('schedule-time').value = schedule.time || '03:30';
    $('schedule-last').textContent = settings.schedule_last_run || '–';
    if (settings.proxy_set) {
      $('proxy').value = '';
      $('proxy').placeholder = `Gesetzt: ${settings.proxy} – leer lassen zum Behalten`;
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
  }

  /* ------------------------------------------------------------------ */
  /* Creators                                                           */
  /* ------------------------------------------------------------------ */

  function updateCreatorSelection() {
    const names = new Set(splitProfiles($('creator-names').value));
    for (const name of state.selectedCreators) names.add(name);
    $('creator-selection').textContent = $('all-subscriptions').checked
      ? 'Alle Abonnements'
      : `${names.size} ausgewählt`;
  }

  async function loadCreators(page = 1) {
    state.creatorQuery = $('creator-search').value.trim();
    const query = encodeURIComponent(state.creatorQuery);
    const data = await api(`/api/creators?page=${page}&q=${query}&per_page=50`);
    state.creatorPage = data.page || 1;
    state.creatorPages = data.pages || 1;
    state.creatorTotal = data.total || 0;
    const list = $('creator-list');
    list.replaceChildren();
    if (!data.items || !data.items.length) {
      const note = document.createElement('p');
      note.className = 'muted';
      note.textContent = state.creatorQuery
        ? 'Keine Treffer.'
        : 'Keine Abonnements gespeichert. „Abonnements laden“ startet einen kurzen Auftrag.';
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
    $('creator-page').textContent = `Seite ${state.creatorPage} / ${state.creatorPages} · ${state.creatorTotal}`;
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
    const data = await api(`/api/folders?path=${encodeURIComponent(path || '')}`);
    state.folderPath = data.path;
    state.folderParent = data.parent;
    state.folderRoot = data.root;
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
      note.textContent = 'Keine Unterordner.';
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
    if (!name) { toast('Bitte einen Ordnernamen eingeben.', 'bad'); return; }
    const button = $('create-folder');
    setBusy(button, true, 'Anlegen …');
    try {
      const data = await api('/api/folders', {
        method: 'POST',
        body: { parent: state.folderPath, name },
      });
      $('new-folder-name').value = '';
      await loadFolder(data.path);
      toast('Ordner angelegt.', 'ok');
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
    setBusy(button, true, dryRun ? 'Scan läuft …' : 'Startet …');
    try {
      $('download-message').textContent = '';
      await startJob('download', options, dryRun ? 'Scan gestartet.' : 'Download gestartet.');
    } catch (error) {
      toast(error.message, 'bad');
    } finally {
      setBusy(button, false);
    }
  }

  async function saveDefaults() {
    const options = collectDownloadOptions(false);
    const button = $('save-defaults');
    setBusy(button, true, 'Speichern …');
    try {
      await api('/api/settings', { method: 'POST', body: { download_defaults: options } });
      toast('Download-Einstellungen gespeichert.', 'ok');
    } catch (error) {
      toast(error.message, 'bad');
    } finally {
      setBusy(button, false);
    }
  }

  async function importSession() {
    const text = $('session-text').value;
    if (!text.trim()) { toast('Bitte eine Sitzung einfügen.', 'bad'); return; }
    const button = $('import-session');
    setBusy(button, true, 'Importiere …');
    try {
      const data = await api('/api/session/import', { method: 'POST', body: { text } });
      $('session-text').value = '';
      toast(`Sitzung importiert (Konto-ID ${data.user_id}). Bitte jetzt testen.`, 'ok');
      await poll();
    } catch (error) {
      toast(error.message, 'bad');
    } finally {
      setBusy(button, false);
    }
  }

  async function testSession() {
    const button = $('test-session');
    setBusy(button, true, 'Prüfe …');
    $('session-result').className = 'result-box';
    $('session-result').textContent = 'Sitzung wird geprüft …';
    try {
      await startJob('test_session', {}, 'Sitzungstest gestartet.');
    } catch (error) {
      $('session-result').className = 'result-box bad';
      $('session-result').textContent = error.message;
      toast(error.message, 'bad');
    } finally {
      setBusy(button, false);
    }
  }

  async function clearSession() {
    if (!window.confirm('Sitzung wirklich vom NAS löschen?')) return;
    try {
      await api('/api/session/clear', { method: 'POST', body: {} });
      toast('Sitzung gelöscht.', 'ok');
      await poll();
    } catch (error) {
      toast(error.message, 'bad');
    }
  }

  async function saveProxy(clear = false) {
    const value = clear ? '' : $('proxy').value.trim();
    if (!clear && !value && state.settings && state.settings.proxy_set) {
      toast('Proxy unverändert. Zum Entfernen „Entfernen“ wählen.');
      return;
    }
    try {
      const data = await api('/api/settings', { method: 'POST', body: { proxy: value } });
      state.settings = { ...(state.settings || {}), ...data };
      if (data.proxy_set) {
        $('proxy').value = '';
        $('proxy').placeholder = `Gesetzt: ${data.proxy} – leer lassen zum Behalten`;
      } else {
        $('proxy').value = '';
        $('proxy').placeholder = 'http://192.168.1.10:8080';
      }
      toast(clear ? 'Proxy entfernt.' : 'Proxy gespeichert.', 'ok');
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
      toast('Regelquelle gespeichert.', 'ok');
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
    setBusy(button, true, 'Speichern …');
    try {
      const data = await api('/api/settings', { method: 'POST', body: { schedule } });
      state.settings = { ...(state.settings || {}), ...data };
      toast('Zeitplan gespeichert.', 'ok');
      await poll();
    } catch (error) {
      toast(error.message, 'bad');
    } finally {
      setBusy(button, false);
    }
  }

  async function requestPreview(relative, kind) {
    try {
      await startJob('preview', {
        path: relative,
        kind,
        output_dir: outputDirValue(),
      }, 'Vorschau wird erzeugt …');
    } catch (error) {
      toast(error.message, 'bad');
    }
  }

  /* ------------------------------------------------------------------ */
  /* Initialisation                                                     */
  /* ------------------------------------------------------------------ */

  function wireEvents() {
    $('refresh-button').addEventListener('click', () => poll());
    $('logout-button').addEventListener('click', async () => {
      try { await api('/api/logout', { method: 'POST', body: {} }); } catch (_) { /* ignore */ }
      window.location.replace('/login');
    });

    $('browse-folder').addEventListener('click', () => openFolderPicker(outputDirValue()));
    $('use-default-folder').addEventListener('click', async () => {
      try {
        const settings = await api('/api/settings');
        const root = settings.share && settings.share.root;
        if (root) $('output-dir').value = `${root}/OnlyFans`;
        else toast('Keine Freigabe gefunden.', 'bad');
      } catch (error) {
        toast(error.message, 'bad');
      }
    });

    $('load-subscriptions').addEventListener('click', async () => {
      const button = $('load-subscriptions');
      setBusy(button, true, 'Lade …');
      try {
        await startJob('subscriptions', {}, 'Abonnements werden geladen.');
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
      if (next !== confirm) { toast('Die neuen Passwörter stimmen nicht überein.', 'bad'); return; }
      const button = event.submitter;
      setBusy(button, true, 'Ändere …');
      try {
        await api('/api/password', {
          method: 'POST',
          body: { current, new: next, confirm },
        });
        $('current-password').value = '';
        $('new-password').value = '';
        $('confirm-password').value = '';
        toast('Passwort geändert.', 'ok');
      } catch (error) {
        toast(error.message, 'bad');
      } finally {
        setBusy(button, false);
      }
    });

    $('folder-close').addEventListener('click', closeFolderPicker);
    $('folder-select').addEventListener('click', () => {
      $('output-dir').value = state.folderPath;
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
      const paused = state.activeJob.status === 'paused';
      try {
        await api(`/api/jobs/${state.activeJob.id}/${paused ? 'resume' : 'pause'}`, {
          method: 'POST', body: {},
        });
        toast(paused ? 'Auftrag fortgesetzt.' : 'Auftrag pausiert.');
        await poll();
      } catch (error) {
        toast(error.message, 'bad');
      }
    });
    $('job-cancel').addEventListener('click', async () => {
      if (!state.activeJob) return;
      if (!window.confirm('Auftrag wirklich abbrechen? Fertige Dateien bleiben erhalten.')) return;
      try {
        await api(`/api/jobs/${state.activeJob.id}/cancel`, { method: 'POST', body: {} });
        toast('Abbruch angefordert.');
        await poll();
      } catch (error) {
        toast(error.message, 'bad');
      }
    });

    $('refresh-library').addEventListener('click', () => poll());
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) poll();
    });
  }

  async function boot() {
    try {
      const session = await api('/api/session');
      state.csrf = session.csrf;
      await loadSettings();
      await poll();
      window.setInterval(() => { if (!document.hidden) poll(); }, 3000);
    } catch (error) {
      if (error.status !== 401) toast(error.message || 'Die Oberfläche konnte nicht geladen werden.', 'bad');
    }
  }

  wireTabs();
  wireEvents();
  boot();
})();
