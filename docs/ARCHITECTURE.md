# Architektur

## Ziel

Ein natives DSM-Paket, das ohne Docker und ohne Container Manager läuft, im
Leerlauf möglichst wenig Arbeitsspeicher belegt und vorhandene Bibliotheken
weiterverwendet. Der vorhandene Python-Kern (`ofdl/`) bleibt die einzige
Download-Engine; Desktop-UI und CLI werden nicht ersetzt.

## Prozessmodell

```
┌────────────────────────────────────────────────────────────┐
│ DSM Package Center / start-stop-status                     │
│   startet genau einen Steuerdienst                         │
└───────────────────────────┬────────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────────┐
│ ofdl.dsm.service  (dauerhaft, klein)                       │
│  • statische Weboberfläche (HTML/CSS/JS)                   │
│  • Anmeldung, CSRF, Passwort, Sitzungsdatei                │
│  • SQLite: Einstellungen, Aufträge, Ereignisse, Creator    │
│  • Zeitplanung                                             │
│  • startet/überwacht den Worker                            │
│  • importiert NUR die Standardbibliothek                   │
└───────────────┬───────────────────────────────┬────────────┘
                │ subprocess (1 Auftrag)        │ HTTP :8765
┌───────────────▼───────────────────┐   ┌───────▼────────────┐
│ ofdl.dsm.worker (kurzlebig)        │   │ Browser            │
│  • Sitzung, API, Regeln            │   │ (LAN, Passwort)    │
│  • Download-Engine / Scan          │   └────────────────────┘
│  • Pillow-Vorschau                 │
│  • SQLite-Manifest im Zielordner   │
│  • beendet sich nach dem Auftrag   │
└────────────────────────────────────┘
```

Der Steuerdienst startet keine Threads für Downloads. Er öffnet den Worker als
Kindprozess, schreibt dessen PID in die Auftragszeile und wartet in einem
Überwachungsthread auf das Ende. Es läuft höchstens **ein** Worker gleichzeitig
(409 bei einem zweiten Start). Pause und Abbruch werden über Spalten in der
Auftragszeile signalisiert; der Worker prüft sie an seinen vorhandenen
`Control.checkpoint()`-Punkten (mindestens alle 0,5 s). Ein Abbruch lässt
abgeschlossene Dateien und resumierbare `.part`-Dateien liegen.

Auf POSIX prüft der Worker zusätzlich, ob sein Elternprozess noch lebt. Stirbt
der Steuerdienst hart, beendet sich der Worker beim nächsten Checkpoint selbst.
Auf Windows ist diese Prüfung deaktiviert, weil `os.getppid()` dort für
abgekoppelte Prozesse unzuverlässig ist.

## Warum der Steuerdienst klein bleibt

`ofdl/dsm/service.py` importiert bewusst **nicht**:

- `requests`, `curl_cffi`, `ofdl.api`, `ofdl.downloads`
- `PIL` / `ofdl.preview`
- `tkinter` / `ofdl.ui`

Ein Test startet einen frischen Python-Prozess, importiert nur den Steuerdienst
und prüft, dass diese Module nicht in `sys.modules` landen. Die schweren
Bibliotheken werden erst im Worker geladen.

Der Dienst hält keine Downloadlisten, keine Dateibaum-Indizes und keine
Vorschaubilder im Speicher. Creator-Listen liegen in SQLite und werden
seitenweise gelesen (50 pro Seite). Ereignisse werden auf die letzten 3000 pro
Auftrag begrenzt; Aufträge auf die letzten 100. Die WAL-Datenbank nutzt einen
Cache von 2 MiB und `temp_store=FILE`.

## SQLite-Schema (Auszug)

```sql
settings(key PRIMARY KEY, value, updated_at)
jobs(id, kind, status, payload, result, error, phase,
     progress_done, progress_total, stats, pid, exit_code,
     pause_requested, cancel_requested, created_at, started_at, finished_at)
events(id, job_id, ts, level, message)          -- letzte 3000 je Auftrag
creators(username PRIMARY KEY, display_name, subscription, scanned_at)
```

`payload` enthält nur die für den Auftrag nötigen Optionen. Ein Proxy mit
Zugangsdaten wird **nicht** im Auftrag gespeichert, sondern in der
Einstellungstabelle (Datei 0600); die Oberfläche erhält nur eine maskierte
Darstellung. Die Sitzung liegt in `session.json` (0600), nie in `settings`.

## Auftragsablauf

1. `POST /api/jobs` validiert die Optionen im Steuerdienst (ohne die schweren
   Module zu importieren) und legt die Auftragszeile an.
2. Der Worker wird mit `PYTHONPATH=<pkgdest>` und einem bereinigten Environment
   gestartet. stdout geht nach `/dev/null`, stderr in `logs/job-<id>.log`.
3. Der Worker markiert den Auftrag als `running`, lädt Sitzung/Regeln/Engine und
   schreibt Fortschritt und Ereignisse gedrosselt in SQLite. Pro Datei werden
   keine großen Objekte gehalten; die Pipeline hat eine Queue von 64 Einträgen.
4. Am Ende schreibt der Worker `completed`, `failed` oder `cancelled` mit einem
   kleinen Ergebnisobjekt. Der Steuerdienst räumt alte Ereignisse/Aufträge auf.
5. Ein abgebrochener oder fehlgeschlagener Worker wird vom Monitor als
   `cancelled`/`failed` markiert, falls er selbst nicht mehr dazu kam.

## Sitzung und Anmeldung

- Die Weboberfläche hat ein eigenes Passwort (PBKDF2-HMAC-SHA256, 600.000
  Iterationen, zufälliges Salt). Es wird bei der Installation über den
  DSM-Wizard gesetzt; ohne Wizard erscheint eine Ersteinrichtungsseite.
- Login setzt ein `HttpOnly`-, `SameSite=Strict`-Cookie mit 12 Stunden Laufzeit.
  Zustandsändernde Requests benötigen zusätzlich einen CSRF-Token. Ein fremder
  `Origin`/`Referer` wird abgelehnt.
- Die OnlyFans-Sitzung wird ausschließlich über den vorhandenen Import
  (`ofdl.auth.parse_session`) eingelesen. Der Import wird nie ausgeführt und
  nicht protokolliert. Ein Sitzungstest ist ein eigener Worker-Auftrag.
- Die Oberfläche zeigt „Importiert“ bis ein Sitzungstest erfolgreich war, danach
  „Verbunden“. Der Status wird in `settings.session_verified` gespeichert.

## Ordner und Berechtigungen

- `conf/resource` legt die Freigabe `OnlyFansDL` an und gibt dem Dienstbenutzer
  `sc-onlyfansdl` Les-/Schreibrecht.
- `conf/privilege` setzt `run-as: package`, den Benutzer `sc-onlyfansdl` und
  `join-groupname: administrators`. Dadurch kann der Nutzer auch eine bestehende
  Bibliothek in einer anderen Freigabe auswählen, ohne SSH oder manuelle
  `chown`-Befehle.
- Der Ordner-Dialog liest nur Verzeichnisnamen (maximal 500 pro Ebene), keine
  Dateiinhalte. Er erlaubt keine Pfade außerhalb der freigegebenen Volumes.
- Vom Dienst neu angelegte Ordner erhalten die Gruppe `administrators` und das
  Setgid-Bit, damit DSM-Benutzer sie im File Station sehen.

## Vereinbarkeit mit vorhandenen Downloads

Die Engine prüft zuerst den erwarteten Pfad und danach das vorhandene
`.ofdl.sqlite3`. Erst wenn beides fehlt, wird der Creator-Baum einmalig nach
alten Layouts durchsucht (LegacyIndex). Es werden keine Dateien gelöscht oder
umbenannt. Ein bestehender Ordner kann im Download-Bereich ausgewählt werden;
die Dateistruktur bleibt unverändert.

## Zeitplanung

Ein einzelner Scheduler-Thread prüft alle 20 Sekunden die Einstellung
`schedule` (aktiv, `HH:MM`, gespeicherte Download-Optionen). Ist die Zeit
erreicht, kein Auftrag aktiv, eine Sitzung vorhanden und heute noch nicht
gelaufen, startet er denselben Worker-Auftragstyp wie ein manueller Download.
Ein verpasster Lauf wird am selben Tag nachgeholt, sofern der Dienst läuft.
Es wird nie ein zweiter Auftrag parallel gestartet.

## Paket-Lebenszyklus

- `postinst`/`postupgrade` legen die venv an, installieren die Wheels offline
  (`--no-index --require-hashes`), prüfen die Importe und setzen beim ersten
  Install das Web-Passwort. Ein Upgrade überschreibt das Passwort nicht.
- `start-stop-status` startet/stoppt den Dienst und schreibt `service.pid`.
- `preupgrade`/`preuninst` stoppen den Dienst.
- `postuninst` entfernt nur private Steuerdaten, venv und Protokolle. Die
  Freigabe und alle Downloads bleiben erhalten.
