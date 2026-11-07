/* Local UI translations. German strings are the source keys. */
(() => {
  'use strict';

  const EN = {
    ...(window.ofdlEnglishExtras || {}),
    'Bibliotheksordner auswählen': 'Choose library folder',
    'Bibliothekspfad': 'Library path',
    'Pfad speichern': 'Save path',
    'In Einstellungen ändern': 'Change in Settings',
    'Bitte zuerst unter Einstellungen einen vorhandenen Ordner auswählen und speichern. Es werden keine Freigaben automatisch angelegt.': 'First choose and save an existing folder in Settings. No shared folders are created automatically.',
    'In DSM: Systemsteuerung → Gemeinsamer Ordner → Bearbeiten → Berechtigungen → Systeminterner Benutzer → sc-onlyfansdl → Lesen/Schreiben. Keine Administratorrechte nötig.': 'In DSM: Control Panel → Shared Folder → Edit → Permissions → System internal user → sc-onlyfansdl → Read/Write. No administrator rights needed.',
    'Ein gemeinsamer Pfad für Downloads, Bibliothek und Zeitplan. Speichern verschiebt und löscht keine Dateien. Neue Unterordner entstehen nur nach ausdrücklichem Anlegen oder beim gestarteten Download.': 'One shared path for downloads, library and schedule. Saving does not move or delete files. Subfolders are created only on explicit request or during a download you start.',
    'Bereits von älteren Versionen angelegte Freigaben bleiben erhalten. Nur selbst in DSM entfernen, nachdem ihr Inhalt geprüft wurde.': 'Shared folders created by older versions are kept. Remove them yourself in DSM only after checking their contents.',
    '. Downloads, Bibliothek und Zeitplan verwenden den gespeicherten Pfad unter Einstellungen. Ohne Manifest sind vorhandene Dateien nicht automatisch gezählt.': '. Downloads, library and schedule use the path saved in Settings. Without a manifest, existing files are not counted automatically.',
    'Das Manifest konnte nicht gelesen werden. Pfad und Berechtigungen prüfen.': 'Could not read the manifest. Check path and permissions.',
    'Bibliothekspfad gespeichert. Dateien wurden nicht verschoben.': 'Library path saved. Files were not moved.',
    'Neuen Unterordner anlegen: {path}?': 'Create new subfolder: {path}?',
    'Bitte zuerst den Bibliothekspfad in den Einstellungen speichern.': 'First save the library path in Settings.',
    'Der Auftrag muss den gespeicherten Bibliothekspfad verwenden.': 'The job must use the saved library path.',
    'Der Bibliothekspfad kann während eines Auftrags nicht geändert werden.': 'The library path cannot be changed during a job.',
    'Der Downloadordner existiert nicht. Bitte einen vorhandenen Ordner wählen oder ausdrücklich anlegen.': 'The download folder does not exist. Choose an existing folder or explicitly create one.',
    'OnlyFans im Browser öffnen': 'Open OnlyFans in browser',
    'Im eigenen Browser anmelden, einschließlich Zwei-Faktor-Anmeldung.': 'Sign in using your own browser, including two-factor authentication.',
    'Entwicklertools (F12) → Netzwerk → eine Anfrage an /api2/v2/ auswählen → Kopieren → Als cURL (bash) kopieren.': 'Developer tools (F12) → Network → select a request to /api2/v2/ → Copy → Copy as cURL (bash).',
    'Unten einfügen und importieren. Danach Sitzung testen.': 'Paste below and import. Then test the session.',
    'Ein eingebettetes Login kann die Sitzung nicht automatisch übernehmen. Passwort und Zwei-Faktor-Code bleiben bei OnlyFans. cURL/HAR enthalten Zugangsdaten: nicht teilen und Exportdateien anschließend löschen.': 'An embedded login cannot capture the session automatically. Password and two-factor code stay with OnlyFans. cURL/HAR contain credentials: do not share them and delete exported files afterwards.',
    'Datei auswählen (HAR/JSON/cURL, max. 2 MB)': 'Choose file (HAR/JSON/cURL, max. 2 MB)',
    'Importdatei ist zu groß (max. 1,9 MB).': 'Import file is too large (max. 1.9 MB).',
    'Datei geladen. Erst Importieren überträgt die Sitzung zum NAS.': 'File loaded. Only Import sends the session to the NAS.',
    // Page titles
    'OnlyFans DL · Anmeldung': 'OnlyFans DL · Sign in',
    'OnlyFans DL · Ersteinrichtung': 'OnlyFans DL · First-time setup',

    // Shell / navigation
    'Dienst wird geprüft …': 'Checking service …',
    'Aktualisieren': 'Refresh',
    'Abmelden': 'Sign out',
    'Übersicht': 'Overview',
    'Sitzung': 'Session',
    'Bibliothek': 'Library',
    'Einstellungen': 'Settings',
    'Auftrag': 'Job',
    'Leerlauf': 'Idle',
    'Kein Auftrag aktiv. Downloads und Bibliotheksscans laufen in einem separaten Prozess und werden nach dem Ende beendet.':
      'No job is active. Downloads and library scans run in a separate process and exit when finished.',
    'Wird vorbereitet …': 'Preparing …',
    'Pause': 'Pause',
    'Abbrechen': 'Cancel',
    'Dienst': 'Service',
    'Online': 'Online',
    'Laufzeit': 'Uptime',
    'Speicher (PSS / RSS)': 'Memory (PSS / RSS)',
    'Downloadordner': 'Download folder',
    'Freigabe': 'Share',
    'Datenträger frei': 'Free space',
    'Letzte Aktivität': 'Recent activity',
    'Noch keine Ereignisse in dieser Sitzung.': 'No events in this session yet.',
    'Letzte Aufträge': 'Recent jobs',
    'Typ': 'Type',
    'Ergebnis': 'Result',
    'Beendet': 'Finished',
    'Noch keine Aufträge.': 'No jobs yet.',

    // Downloads
    'Zielordner': 'Destination',
    'Durchsuchen': 'Browse',
    'Standard': 'Default',
    'Der Ordner liegt auf dem NAS. Bestehende Dateien, Unterordner und':
      'The folder is on the NAS. Existing files, subfolders and',
    'werden weiterverwendet.': 'are reused.',
    'Alle aktiven Abonnements verwenden': 'Use all active subscriptions',
    'Nur diese Creator (Namen oder Profil-URLs, durch Komma/Zeile getrennt)':
      'Only these creators (names or profile URLs, separated by comma/line)',
    'Abonnements laden': 'Load subscriptions',
    'Auswahl löschen': 'Clear selection',
    '0 ausgewählt': '0 selected',
    'Noch keine Abonnementliste geladen. „Abonnements laden“ startet einen kurzen Auftrag.':
      'No subscription list loaded yet. “Load subscriptions” starts a short job.',
    'Zurück': 'Back',
    'Seite 1': 'Page 1',
    'Weiter': 'Next',
    'Inhalte und Filter': 'Content and filters',
    'Kategorien': 'Categories',
    'Archiviert': 'Archived',
    'Nachrichten': 'Messages',
    'Gekauft': 'Purchased',
    'Dateitypen': 'Media types',
    'Fotos': 'Photos',
    'Optionen': 'Options',
    'Alben-Unterordner': 'Album subfolders',
    'Kategorie-Unterordner': 'Category subfolders',
    'Vorschau erlauben, wenn Original fehlt': 'Allow preview when original is missing',
    'Nur die letzten Tage (0 = alle)': 'Last days only (0 = all)',
    'Start': 'Start',
    'Download starten': 'Start download',
    'Nur suchen (Scan)': 'Scan only',
    'Als Zeitplan-Standard speichern': 'Save as schedule default',

    // Session
    'Sitzungsstatus': 'Session status',
    'Unbekannt': 'Unknown',
    'Konto-ID': 'Account ID',
    'Ablage': 'Storage',
    'Die Sitzung wird nur auf dem NAS gespeichert. Sie wird nie an Dritte gesendet und nicht in Einstellungen oder Protokollen abgelegt.':
      'The session is stored only on this NAS. It is never sent to third parties and is not written to settings or logs.',
    'Sitzung testen': 'Test session',
    'Sitzung löschen': 'Delete session',
    'Sitzung importieren': 'Import session',
    'cURL (bash), HAR, JSON oder Roh-Header aus deinem eingeloggten Browser':
      'cURL (bash), HAR, JSON or raw headers from your logged-in browser',
    'Importieren': 'Import',
    'Kopiere eine Anfrage an': 'Copy a request to',
    '. Der Import wird nie ausgeführt. Ein HAR kann groß sein; maximal 2 MB.':
      '. The import is never executed. A HAR can be large; maximum 2 MB.',
    'Netzwerk': 'Network',
    'Optionaler Proxy (http://, https://, socks5://, socks5h://)':
      'Optional proxy (http://, https://, socks5://, socks5h://)',
    'Speichern': 'Save',
    'Entfernen': 'Remove',
    'Der Proxy wird für API, Regeln und Medien verwendet. Zugangsdaten werden in der Oberfläche maskiert. Leer lassen für direkt.':
      'The proxy is used for the API, rules and media. Credentials are masked in the UI. Leave empty for direct.',
    'Regelquelle (HTTPS-URL oder lokaler JSON-Pfad)':
      'Rules source (HTTPS URL or local JSON path)',

    // Library
    'Ordner': 'Folder',
    'Einträge': 'Entries',
    'Erfasste Größe': 'Recorded size',
    'Schreibbar': 'Writable',
    'Freier Platz': 'Free space',
    'Die Zählung kommt aus dem vorhandenen': 'The count comes from the existing',
    'und liest keine Mediendateien. Ein bestehender Ordner kann im Download-Bereich ausgewählt werden; die Dateistruktur bleibt unverändert.':
      'and does not read media files. An existing folder can be selected in the Download section; the file structure remains unchanged.',
    'Hinweise für große Bibliotheken': 'Notes for large libraries',
    'Die Oberfläche lädt nie die ganze Bibliothek. Creator-Listen und Ereignisse sind seitenweise und begrenzt.':
      'The UI never loads the whole library. Creator lists and events are paged and bounded.',
    'Der Steuerdienst hält keine Downloadlisten, Dateiverzeichnisse oder Vorschaudaten im Speicher.':
      'The control service keeps no download lists, directory trees or preview data in memory.',
    'Der Worker verarbeitet Medien als Datenstrom und beendet sich nach dem Auftrag.':
      'The worker streams media and exits after the job.',
    'Bei rund 80.000 Dateien kann ein Erstlauf länger dauern; spätere Läufe nutzen das Manifest und exakte Pfade.':
      'With about 80,000 files the first run can take longer; later runs use the manifest and exact paths.',

    // Settings
    'Zeitplan': 'Schedule',
    'Täglicher Download automatisch starten': 'Start daily download automatically',
    'Uhrzeit (NAS-Zeit)': 'Time (NAS time)',
    'Zeitplan speichern': 'Save schedule',
    'Der Zeitplan verwendet die aktuellen Download-Einstellungen aus dem Download-Bereich. Es läuft nie mehr als ein Auftrag gleichzeitig. Ein verpasster Lauf wird am selben Tag nachgeholt, sofern der Dienst dann läuft.':
      'The schedule uses the current download settings from the Download section. Never more than one job runs at a time. A missed run is caught up on the same day if the service is running.',
    'Letzter Lauf': 'Last run',
    'Nächster Lauf': 'Next run',
    'Passwort ändern': 'Change password',
    'Aktuelles Passwort': 'Current password',
    'Neues Passwort (mindestens 10 Zeichen)': 'New password (at least 10 characters)',
    'Neues Passwort wiederholen': 'Repeat new password',
    'Über das Paket': 'About the package',
    'App-Version': 'App version',
    'Paketversion': 'Package version',
    'Prozessmodell': 'Process model',
    '1 Steuerdienst + 1 kurzlebiger Worker': '1 control service + 1 short-lived worker',
    'Speicherziel': 'Memory target',
    '≤ 50 MiB PSS im Leerlauf (auf DS723+ zu messen)': '≤ 50 MiB PSS idle (to be measured on DS723+)',
    'Desktop-App und CLI bleiben im Paket enthalten. Diese Oberfläche ist eine statische Browseroberfläche; sie lädt keine externen Schriftarten, Skripte oder Bilder.':
      'The desktop app and CLI remain in the package. This interface is a static browser UI; it loads no external fonts, scripts or images.',

    // Folder dialog
    'Downloadordner wählen': 'Choose download folder',
    'Schließen': 'Close',
    'Übergeordnet': 'Parent',
    'Anlegen': 'Create',
    'Diesen Ordner wählen': 'Choose this folder',
    'Keine Unterordner.': 'No subfolders.',

    // Login / setup
    'Synology DSM · geschützte Weboberfläche': 'Synology DSM · protected web interface',
    'Passwort': 'Password',
    'Anmelden': 'Sign in',
    'Das Passwort wurde bei der Paketinstallation festgelegt. Es wird nur auf diesem NAS gespeichert.':
      'The password was set during package installation. It is stored only on this NAS.',
    'Das Passwort muss mindestens 10 Zeichen lang sein.': 'The password must be at least 10 characters long.',
    'Die Passwörter stimmen nicht überein.': 'The passwords do not match.',
    'Anmeldung fehlgeschlagen.': 'Sign-in failed.',
    'Wird gespeichert …': 'Saving …',
    'Wird angemeldet …': 'Signing in …',
    'Ersteinrichtung': 'First-time setup',
    'Lege das Passwort für die Weboberfläche fest.': 'Set the password for the web interface.',
    'Passwort wiederholen': 'Repeat password',
    'Passwort speichern': 'Save password',
    'Das Paket legt normalerweise bereits bei der Installation ein Passwort an. Diese Seite erscheint nur, wenn das nicht geschehen ist.':
      'The package normally sets a password during installation. This page appears only if that did not happen.',

    // Dynamic UI
    'Alle Abonnements': 'All subscriptions',
    '{n} ausgewählt': '{n} selected',
    'Keine Treffer.': 'No matches.',
    'Keine Abonnements gespeichert. „Abonnements laden“ startet einen kurzen Auftrag.':
      'No subscriptions stored. “Load subscriptions” starts a short job.',
    'Seite {page} / {pages} · {total}': 'Page {page} / {pages} · {total}',
    'Keine Freigabe gefunden.': 'No share found.',
    'Ordner angelegt.': 'Folder created.',
    'Bitte einen Ordnernamen eingeben.': 'Enter a folder name.',
    'Bitte einen Downloadordner auswählen.': 'Please choose a download folder.',
    'Bitte Creator auswählen oder „Alle aktiven Abonnements“ aktivieren.':
      'Select creators or enable “All active subscriptions”.',
    'Mindestens eine Inhaltskategorie auswählen.': 'Select at least one content category.',
    'Mindestens einen Dateityp auswählen.': 'Select at least one media type.',
    'Download gestartet.': 'Download started.',
    'Scan gestartet.': 'Scan started.',
    'Startet …': 'Starting …',
    'Scan läuft …': 'Scan running …',
    'Speichern …': 'Saving …',
    'Anlegen …': 'Creating …',
    'Importiere …': 'Importing …',
    'Prüfe …': 'Checking …',
    'Lade …': 'Loading …',
    'Ändere …': 'Changing …',
    'Sitzung wird geprüft …': 'Checking session …',
    'Sitzungstest gestartet.': 'Session test started.',
    'Abonnements werden geladen.': 'Loading subscriptions.',
    'Sitzung importiert (Konto-ID {id}). Bitte jetzt testen.':
      'Session imported (account ID {id}). Please test it now.',
    'Sitzung gelöscht.': 'Session deleted.',
    'Proxy gespeichert.': 'Proxy saved.',
    'Proxy entfernt.': 'Proxy removed.',
    'Proxy unverändert. Zum Entfernen „Entfernen“ wählen.':
      'Proxy unchanged. Choose “Remove” to delete it.',
    'Gesetzt: {proxy} – leer lassen zum Behalten':
      'Set: {proxy} – leave empty to keep',
    'Regelquelle gespeichert.': 'Rules source saved.',
    'Zeitplan gespeichert.': 'Schedule saved.',
    'Download-Einstellungen gespeichert.': 'Download settings saved.',
    'Passwort geändert.': 'Password changed.',
    'Die neuen Passwörter stimmen nicht überein.': 'The new passwords do not match.',
    'Bitte eine Sitzung einfügen.': 'Please paste a session.',
    'Bitte zuerst eine Sitzung importieren.': 'Please import a session first.',
    'Die Oberfläche konnte nicht geladen werden.': 'The interface could not be loaded.',
    'Es ist keine Sitzung eingerichtet. Bitte zuerst eine Sitzung importieren und testen.':
      'No session configured. Import and test a session first.',
    'Es ist keine Sitzung eingerichtet. Bitte zuerst eine Sitzung importieren.':
      'No session configured. Import a session first.',
    'Es ist noch kein Passwort eingerichtet.': 'No password is configured yet.',
    'Passwort falsch.': 'Wrong password.',
    'Zu viele fehlgeschlagene Anmeldungen. Bitte eine Minute warten.':
      'Too many failed sign-ins. Wait one minute.',
    'Der Downloadordner ist nicht beschreibbar. Prüfe die Freigabeberechtigung.':
      'The download folder is not writable. Check the share permission.',
    'Der Downloadordner konnte nicht angelegt werden. Prüfe Pfad und Berechtigungen.':
      'The download folder could not be created. Check path and permissions.',
    'Der Ordner liegt außerhalb der freigegebenen Volumes.':
      'The folder is outside the allowed volumes.',
    'Der Ordner kann nicht gelesen werden.': 'The folder cannot be read.',
    'Der Ordner ist nicht beschreibbar.': 'The folder is not writable.',
    'Vorschau wird erzeugt …': 'Creating preview …',
    'Auftrag pausiert.': 'Job paused.',
    'Auftrag fortgesetzt.': 'Job resumed.',
    'Abbruch angefordert.': 'Cancel requested.',
    'Auftrag wirklich abbrechen? Fertige Dateien bleiben erhalten.':
      'Really cancel the job? Finished files are kept.',
    'Sitzung wirklich vom NAS löschen?': 'Really delete the session from the NAS?',
    'Download fertig: {n} neu, {e} vorhanden.': 'Download finished: {n} new, {e} existing.',
    'Download abgebrochen. Fertige Dateien bleiben erhalten.':
      'Download cancelled. Finished files are kept.',
    'Download fehlgeschlagen.': 'Download failed.',
    'Vorschau nicht verfügbar.': 'Preview not available.',
    'Sitzungstest fehlgeschlagen.': 'Session test failed.',
    'Sitzung wurde vom Konto-Endpunkt akzeptiert.': 'Session accepted by the account endpoint.',
    'Sitzung akzeptiert.': 'Session accepted.',
    'Sitzung wird geprüft': 'Checking session',
    'Ermittlung läuft …': 'Scanning …',
    'Keine Fortschrittsdaten': 'No progress data',
    '{done} / {total} Dateien': '{done} / {total} files',
    '{n} neu · {e} vorhanden · {f} Fehler': '{n} new · {e} existing · {f} errors',
    '{n} Abonnements': '{n} subscriptions',
    '{n} Abonnements geladen.': '{n} subscriptions loaded.',
    '{n} Ereignisse': '{n} events',
    'Noch keine Ereignisse in diesem Auftrag.': 'No events in this job yet.',
    '{free} frei von {total}': '{free} free of {total}',

    // Status / job labels
    'Wartet': 'Queued',
    'Läuft': 'Running',
    'Pausiert': 'Paused',
    'Fertig': 'Done',
    'Fehler': 'Error',
    'Abgebrochen': 'Cancelled',
    'Sitzungstest': 'Session test',
    'Abonnements': 'Subscriptions',
    'Vorschau': 'Preview',
    'Fortsetzen': 'Resume',
    'Neu': 'New',
    'Vorhanden': 'Existing',
    'Geplant': 'Planned',
    'Gefiltert': 'Filtered',
    'Nicht verfügbar': 'Unavailable',
    'Übertragen': 'Transferred',
    'Verbunden': 'Connected',
    'Importiert': 'Imported',
    'Nicht eingerichtet': 'Not configured',
    'Einrichtung erforderlich': 'Setup required',
    'Einrichtung': 'Setup',
    'Dienst online': 'Service online',
    'Dienst nicht erreichbar': 'Service unreachable',
    'vorhanden': 'present',
    'neu / leer': 'new / empty',
    'ja': 'yes',
    'nein': 'no',
    'frei': 'free',
    'läuft': 'running',
    'Abgebrochen. Abgeschlossene Dateien bleiben erhalten; partielle Dateien können fortgesetzt werden.':
      'Cancelled. Finished files are kept; partial files can resume.',
    'Mehrfach': 'Multiple'
  };

  const PLACEHOLDER_EN = {
    'creator1, creator2': 'creator1, creator2',
    'Creator suchen …': 'Search creators …',
    'http://192.168.1.10:8080': 'http://192.168.1.10:8080',
    'Standard: DATAHOARDERS dynamic-rules': 'Default: DATAHOARDERS dynamic-rules',
    'Neuer Unterordner': 'New subfolder'
  };

  const ARIA_EN = {
    'Status des Steuerdienstes': 'Control service status',
    'Bereiche': 'Sections',
    'Downloadordner': 'Download folder',
    'Creator suchen': 'Search creators',
    'Neuer Unterordner': 'New subfolder',
    'Sprache / Language': 'Language'
  };

  const languages = { de: 'Deutsch', en: 'English', fr: 'Français', es: 'Español', it: 'Italiano', nl: 'Nederlands', pt: 'Português' };
  let stored = '';
  try { stored = localStorage.getItem('ofdl_lang') || ''; } catch (_) { /* Private browsing. */ }
  const preferred = String(navigator.language || 'en').toLowerCase().split('-')[0];
  let mode = Object.hasOwn(languages, stored) ? stored : 'auto';
  let lang = mode === 'auto' ? (Object.hasOwn(languages, preferred) ? preferred : 'en') : mode;
  let source = mode === 'auto' ? 'browser' : 'manual';
  let resolveReady;
  const ready = new Promise((resolve) => { resolveReady = resolve; });
  let originalTitle = document.title;
  const textOriginals = new WeakMap();
  const attrOriginals = new WeakMap();
  const reverse = new Map();
  for (const [source, value] of Object.entries({ ...EN, ...PLACEHOLDER_EN, ...ARIA_EN })) {
    reverse.set(value, source);
    for (const catalog of Object.values(window.ofdlLanguages || {})) {
      if (catalog[value]) reverse.set(catalog[value], source);
    }
  }

  function sourceKey(text) { return Object.hasOwn(EN, text) ? text : (reverse.get(text) || text); }

  function translate(text, vars) {
    const source = sourceKey(text);
    const english = EN[source] || PLACEHOLDER_EN[source] || ARIA_EN[source] || source;
    let value = lang === 'de' ? source : ((window.ofdlLanguages?.[lang] || {})[english] || english);
    if (vars) {
      for (const [key, replacement] of Object.entries(vars)) {
        value = value.replaceAll(`{${key}}`, String(replacement));
      }
    }
    return value;
  }

  function applyTextNodes(root) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        const parent = node.parentElement;
        if (!parent) return NodeFilter.FILTER_REJECT;
        if (['SCRIPT', 'STYLE', 'OPTION', 'TEXTAREA'].includes(parent.tagName)) return NodeFilter.FILTER_REJECT;
        return node.nodeValue.trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
      }
    });
    let node;
    while ((node = walker.nextNode())) {
      let record = textOriginals.get(node);
      if (!record || record.last !== node.nodeValue) record = { source: node.nodeValue, last: '' };
      const source = record.source;
      const key = source.trim();
      const translated = translate(key);
      if (translated !== key) {
        const leading = source.match(/^\s*/)[0];
        const trailing = source.match(/\s*$/)[0];
        node.nodeValue = leading + translated + trailing;
      } else {
        node.nodeValue = source;
      }
      record.last = node.nodeValue;
      textOriginals.set(node, record);
    }
  }

  function applyAttributes(selector, attribute, map) {
    document.querySelectorAll(selector).forEach((element) => {
      if (attribute === 'placeholder' && element.id === 'proxy') return;
      let values = attrOriginals.get(element);
      if (!values) { values = {}; attrOriginals.set(element, values); }
      if (!(attribute in values)) values[attribute] = element.getAttribute(attribute) || '';
      const source = values[attribute];
      if (source) element.setAttribute(attribute, translate(source));
    });
  }

  function applyDom() {
    document.documentElement.lang = lang;
    document.title = translate(originalTitle);
    applyTextNodes(document.body);
    applyAttributes('[placeholder]', 'placeholder', PLACEHOLDER_EN);
    applyAttributes('[aria-label]', 'aria-label', ARIA_EN);
    document.querySelectorAll('#language-select').forEach((select) => { select.value = mode; });
  }

  async function setLanguage(next) {
    mode = Object.hasOwn(languages, next) ? next : 'auto';
    if (mode === 'auto') await detectLanguage();
    else { lang = mode; source = 'manual'; }
    try { localStorage.setItem('ofdl_lang', mode); } catch (_) { /* Private browsing. */ }
    applyDom();
    document.dispatchEvent(new CustomEvent('ofdl-language', { detail: lang }));
  }

  function normalizeLanguage(value) {
    const aliases = { ger: 'de', enu: 'en', fre: 'fr', spn: 'es', ita: 'it', nld: 'nl', ptg: 'pt', ptb: 'pt' };
    const text = String(value || '').toLowerCase().split(/[-_]/)[0];
    const language = aliases[text] || text;
    return Object.hasOwn(languages, language) ? language : '';
  }

  async function detectLanguage() {
    let hint = '';
    try {
      hint = normalizeLanguage(new URLSearchParams(location.search).get('dsm_lang'));
      if (!hint) {
        for (const cookie of document.cookie.split(';')) {
          const [key, value] = cookie.trim().split('=');
          if (['lang', 'language'].includes(key)) hint = normalizeLanguage(decodeURIComponent(value || ''));
          if (hint) break;
        }
      }
    } catch (_) { /* Missing/inaccessible DSM locale cookie. */ }
    if (hint) { lang = hint; source = 'dsm-hint'; return; }
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 2000);
    try {
      const response = await fetch('/api/locale', { signal: controller.signal, cache: 'no-store' });
      if (response.ok) hint = normalizeLanguage((await response.json()).language);
    } catch (_) { /* Standalone/local run or unavailable DSM config. */ }
    finally { clearTimeout(timer); }
    if (mode !== 'auto') return;
    lang = hint || normalizeLanguage(navigator.language) || 'en';
    source = hint ? 'dsm-system' : 'browser';
  }

  async function init() {
    document.querySelectorAll('#language-select').forEach((select) => {
      select.replaceChildren(...Object.entries({ auto: 'Auto · DSM / Browser', ...languages }).map(([value, label]) => {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = label;
        return option;
      }));
      select.value = mode;
      select.addEventListener('change', () => setLanguage(select.value));
    });
    if (mode === 'auto') await detectLanguage();
    applyDom();
    resolveReady();
  }

  window.ofdlI18n = {
    t: translate,
    setLanguage,
    getLanguage: () => lang,
    getSource: () => source,
    ready,
    apply: applyDom,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
