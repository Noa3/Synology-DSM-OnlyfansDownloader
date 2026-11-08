# Testbericht — OnlyFans DL für Synology DSM 2.8.0-8

Build-Datum: **2026-11-07**
Zielplattform: **Synology DS723+ (r1000), DSM 7.2, Python 3.13 aus SynoCommunity**
Testumgebung: Windows 11, CPython 3.13.12, Chromium/Playwright

> **Klarstellung:** Die Spalte „DSM“ ist in dieser Build-Umgebung **nicht
> ausgeführt** worden, weil kein Zugriff auf die DS723+ bestand (kein SSH, kein
> erreichbarer NAS-Host). Alle mit „DSM: AUSSTEHEND“ markierten Prüfungen sind
> auf dem Zielgerät nachzuholen. Sie werden hier nicht als bestanden
> deklariert. Die lokalen Tests prüfen Code, Paketaufbau, UI und
> Speicherverhalten, ersetzen aber keinen DSM-Installationstest.

## Ergebnisübersicht

| Prüfung | Ergebnis | Ort |
| --- | --- | --- |
| Vollständige Python-Testsuite | **363 Tests, 0 Fehler, 3 Skips** | lokal |
| DSM-spezifische Tests | **70 Tests, 0 Fehler, 2 Linux-Skips** | lokal |
| DSM-spezifische Tests inkl. echter Prozessgruppen | **70 Tests, 0 Fehler, keine Skips** | Linux-CI |
| Paketbau | **bestanden** | lokal |
| Reproduzierbarer Bau (zweimal) | **byte-identisch** | lokal |
| Browser-UI (Playwright) | **bestanden**, keine Konsolenfehler | lokal |
| Speichermessung Steuerdienst | **ca. 33 MiB RSS / 18,5 MiB private** | früherer lokaler Build, nicht neu gemessen |
| Streaming-Worker 256 MiB | **Peak ca. 37,3 MiB RSS / 28,2 MiB private** | früherer lokaler Build, nicht neu gemessen |
| Installation auf DS723+ | **AUSSTEHEND** | DSM |
| Start/Stop auf DSM | **AUSSTEHEND** | DSM |
| NAS-Neustart | **AUSSTEHEND** | DSM |
| Update/Erhalt der Downloads | **AUSSTEHEND** | DSM |
| PSS im Leerlauf auf DS723+ | **AUSSTEHEND** | DSM |
| Echte OnlyFans-Sitzung / API | **AUSSTEHEND** | Zielkonto |

Windows überspringt den Symlink-Rechtetest sowie zwei echte Linux-Prozesstests.
Letztere prüfen eine verwaiste Worker-Kindgruppe und das Stoppen des Dienstes
bei fehlender PID-Datei. Sie werden in der Linux-CI ausgeführt, nicht als native
DSM-Tests ausgegeben.

## Ausgeführter Befehl

```bash
python -m unittest discover -s tests
```

Auszug:

```
Ran 366 tests in 74.378s
OK (skipped=3)
```

Die DSM-Tests umfassen:

| Datei | Inhalt |
| --- | --- |
| `tests/test_dsm_security.py` | Passwort-Hashing, SessionStore 0600, Redaktion, Login-Limiter |
| `tests/test_dsm_db.py` | Schema, Jobs, Ereignis-/Auftragsbegrenzung, Creator-Seiten, Manifest-Statistik |
| `tests/test_dsm_jobs.py` | Optionsvalidierung, Pfadgrenzen, Profile, Proxy, Zeitplan |
| `tests/test_dsm_worker.py` | Pause/Abbruch, EventWriter, Preview, Abonnements, Download-Mapping |
| `tests/test_dsm_service.py` | Setup/Login/CSRF, Rechte, Ordner, Jobs, Preview, statische Dateien, Rate-Limit, leichter Import |
| `tests/test_dsm_package.py` | INFO, Checksumme, Inhalte, Rechte, JSON, Shell-Syntax, Reproduzierbarkeit |
| `tests/test_dsm_resilience.py` | Thread-Fortschritt, Schreibsperren, NaN-JSON, Ereignis-Tail, Sitzungswechsel, DSM-Locale, Free-Resub-Preisschutz, API-Backoff, PID-Reuse und Linux-Prozessbäume |

Zusätzlich prüft `test_dsm_service.py` in einem frischen Prozess, dass der
Steuerdienst **nicht** `requests`, `curl_cffi`, `PIL`, `ofdl.api` oder
`ofdl.downloads` importiert.

## Paketprüfung

```
Datei:  dist/OnlyFansDL-r1000-dsm72_2.8.0-8.spk
Größe: 22,01 MiB
SHA256: 9bb5d9b03e3f65cd14e8e342cab01d706d5f53d6733c0bb4d4cb9804a726e580
MD5(package.tgz): b3249765d99fc53ff159ccb6f4a37b35
```

Geprüft:

- `INFO`: `package=OnlyFansDL`, `version=2.8.0-8`, `arch=r1000`,
  `os_min_ver=7.2-64570`, `adminport=8765`, `adminurl=/`,
  `install_dep_packages=python313>=3.13.11-9`, MD5-Checksumme stimmt.
- `package.tgz`: `ofdl/dsm/service.py`, `ofdl/dsm/worker.py`,
  `web/index.html`, `web/static/app.js`, `ui/config`,
  `requirements-dsm.lock`, 11 Wheels; **keine** `__pycache__`, `.pyc`,
  `session.json` oder `control.sqlite3`.
- Skripte `postinst`, `postupgrade`, `start-stop-status` sind `0755`;
  `postinst` enthält `ACTION="install"`, `postupgrade` `ACTION="upgrade"`;
  kein `@ACTION@` mehr.
- `conf/privilege`, `conf/resource`, `WIZARD_UIFILES/*`, `ui/config` sind
  gültiges JSON; `bash -n` parst alle Shell-Skripte.
- `conf/privilege`: `run-as: package`, `sc-onlyfansdl`, `groupname: synocommunity`,
  **kein** `join-groupname`, **kein** `ctrl-script`; entspricht dem Muster
  funktionierender SynoCommunity-Pakete.
- `conf/resource`: leer, keine `data-share`-Ressource. Keine automatische
  Freigabeerstellung oder Berechtigungserteilung. Installer/Start exportieren
  keinen automatisch ermittelten Freigabepfad.
- Zwei Builds mit `SOURCE_DATE_EPOCH=1794009600` sind byte-identisch.

  Windows-Build und Linux-CI-Build haben beide den oben genannten SHA256.
  Der Release-Asset ist der lokal geprüfte Windows-Build. Abweichende zukünftige
  zlib-Versionen könnten andere gzip-Bytes erzeugen.

## Browser-UI

`python tools/test_web_ui.py` mit Playwright (Chromium, headless, 1440×1100)
prüft mit synthetischer Sitzung und lokalen Manifesten, ohne echtes Konto:

- Setup/Login und Hauptoberfläche mit sieben Sprachen; simulierte DSM-System-
  sprache und Sprachcookie, manueller Vorrang und Rückkehr zu Auto
- Erster Start ohne Bibliothek → Einstellungen, kein impliziter Zielordner
- Gespeicherter Pfad für Downloads und Bibliothek; Manifestwechsel sofort sichtbar
- Ordnererstellung: Bestätigung ablehnen erzeugt nichts, Bestätigung erlauben
  erstellt nur den ausdrücklich gewählten Unterordner
- Dateiauswahl sendet keine Sitzung; Import erst nach ausdrücklichem Klick
- Sprachenwechsel durch alle Tabs, Pfad bleibt korrekt; Neuladen behält Pfad
- Abmelden/Login ohne beschädigte HTTP-Folgeanfrage
- Reload während laufendem Auftrag: Status und letzte 100 Ereignisse erscheinen
- Ausfall nur der Ereignisabfrage: Dienst bleibt online, Auftrag bleibt sichtbar
- Fehlgeschlagener Erstaufruf: automatischer neuer Versuch ohne manuelles Reload
- Unbekannte Scan-Gesamtmenge ohne Prozentzahl; separate Datei-Byteanzeige;
  nach Ende der Suche plausibler Gesamtfortschritt und sichtbare 401-Fehler
- Mobile Breite 375 px ohne Überlauf in Übersicht, Free & Trials und Einstellungen
- keine `console.error`/`pageerror`-Meldungen
- keine externen Ressourcen (CSP-konform)

Aktuelle Dashboard-Screenshots sind synthetische lokale Tests, keine NAS-/
echten Downloadmessungen: `docs/dsm-ui-dashboard.png`, `docs/dsm-ui-dashboard-en.png`.
Ältere illustrative Screenshots (nicht der aktuelle Speicher-Dialog):
`docs/dsm-ui-folders.png`, `docs/dsm-ui-session.png`,
`docs/dsm-ui-session-tested.png`, `docs/dsm-ui-settings.png`.

## Speichermessung (lokal, nur Indiz)

Die Messung erfolgte unter Windows. PSS ist dort nicht verfügbar; die
DSM-Zielmarke bezieht sich auf PSS und muss mit `tools/measure_dsm.py` auf der
DS723+ gemessen werden. Die folgenden Werte stammen aus der früheren Messung,
nicht aus einem erneuten Speicherbenchmark von 2.8.0-8.

| Zustand | Prozesse | RSS | Private |
| --- | --- | ---: | ---: |
| Dienst nach Start | Dienst + venv-Launcher | 33,0 MiB | 18,5 MiB |
| UI-Ressourcen geladen | Dienst + Launcher | 33,6 MiB | 18,9 MiB |
| Nach 5 Vorschau-Aufträgen | Dienst + Launcher | 33,9 MiB | 19,0 MiB |
| Streaming-Worker, 256 MiB | Worker + Launcher | **37,3 MiB Peak** | 28,2 MiB |
| Import-Baseline Download-Worker | Worker + Launcher | 39,6 MiB | 28,0 MiB |

Der Streaming-Test verwendet den echten `run_downloads`-Pfad (Manifest,
Byte-Range-Prüfung, 256-KiB-Chunks, `.part`-Handling) gegen eine lokale
HTTP-Quelle; nur die Host-/Portprüfung war für den Test gelockert. Der Worker
lädt die Datei nicht in den Speicher. Details: `docs/MEASUREMENT.md`.

## DSM-Testmatrix (auf der DS723+ nachzuholen)

| # | Prüfung | Vorgehen | Status |
| --- | --- | --- | --- |
| 1 | Paketquelle + Python 3.13 | SynoCommunity-Quelle, `python313` installieren | AUSSTEHEND |
| 2 | SPK-Installation | Package Center → Manuell installieren | AUSSTEHEND |
| 3 | Wizard/Passwort | Passwort setzen, Oberfläche öffnen | AUSSTEHEND |
| 4 | Start/Stop | Package Center starten/stoppen; `start-stop-status` | AUSSTEHEND |
| 5 | NAS-Neustart | NAS neu starten, Dienst und Oberfläche prüfen | AUSSTEHEND |
| 6 | Update | neue SPK über die alte installieren; Downloads/Manifest erhalten | AUSSTEHEND |
| 7 | Deinstallation | Freigabe/Downloads bleiben erhalten | AUSSTEHEND |
| 8 | Sitzungsimport + Test | echte API-Anfrage importieren, Test | AUSSTEHEND |
| 9 | Download | kleiner Creator, Datei + Manifest prüfen | AUSSTEHEND |
| 10 | Große Bibliothek | ~80.000 Dateien, Scan/Download, Abbruch | AUSSTEHEND |
| 11 | PSS idle | `measure_dsm.py sample --seconds 30 --interval 2` | AUSSTEHEND |
| 12 | PSS mit UI | Browser offen, 2 min, dann messen | AUSSTEHEND |
| 13 | PSS aktiv | großer Auftrag, `--interval 0.5` | AUSSTEHEND |
| 14 | PSS nach Abbruch | 30 s warten, Worker beendet? | AUSSTEHEND |
| 15 | Mehrfachläufe | Sequenz 3×, Rückkehr zum Ausgangswert | AUSSTEHEND |
| 16 | Upgrade-Speicherzustimmung | Kein alter Pfad aktiv, bis in Einstellungen gespeichert | AUSSTEHEND |
| 17 | Keine neuen Freigaben | Installation/Start legt weder OnlyFans noch OnlyFansDL an | AUSSTEHEND |
| 18 | Benutzerrechte | Nur ausdrücklich gewählte Freigabe für sc-onlyfansdl erlaubt | AUSSTEHEND |
| 19 | Vollständiges Stoppen | Dienst + Worker + ffmpeg bei aktivem/pausiertem/hängendem Auftrag beenden | AUSSTEHEND |
| 20 | Echte Sitzungsprobleme | Browser/NAS parallel, 401/429/Netzfehler und kontrollierte Erholung prüfen | AUSSTEHEND |
| 21 | Free-Resub | Nur autorisierte kostenlose Profile, echte API-Kompatibilität | AUSSTEHEND |

### Befehle für die DSM-Messung

`tools/measure_dsm.py` auf das NAS kopieren (z. B. in die Freigabe) und mit dem
SynoCommunity-Python ausführen:

```bash
PY=/var/packages/python313/target/bin/python3
$PY /volume1/OnlyFans/tools/measure_dsm.py snapshot --json
$PY /volume1/OnlyFans/tools/measure_dsm.py sample --seconds 30 --interval 2
```

Die Oberfläche zeigt unter **Übersicht → Dienst → Speicher** zusätzlich PSS/RSS
des Dienstes und des aktiven Workers an.

## Bekannte, nicht geprüfte Punkte

Linux-CI auf Implementierungscommit `accbee631c2f45fed9a0054ba0ab88fc42eaec8e`:
[`42527913130`](https://github.com/Noa3/Synology-DSM-OnlyfansDownloader/actions/runs/42527913130),
`Ran 72 tests in 22.185s`, `OK`, keine Skips. Enthält die echten Linux-Tests
für Worker-Kindgruppen und Dienststop ohne PID-Datei. **Kein DSM-Hardwaretest.**

- **Keine echte OnlyFans-Sitzung** und kein echter Mediendownload in dieser
  Umgebung. Die API-/Signatur-/Cloudflare-Kompatibilität kann sich ändern.
- **Keine DSM-Hardware**: Installation, Start/Stop, Neustart, Update,
  Berechtigungen, SynoCommunity-Abhängigkeit und PSS wurden nicht auf einer
  DS723+ ausgeführt.
- **Keine 80.000-Dateien-Bibliothek** auf NAS-Hardware. Die Engine-Tests und die
  Manifest-/Legacy-Tests decken die Logik ab; die reale Scan-Dauer hängt von
  Speicher und HDD/SSD ab.
- **PSS** ist nur auf Linux verfügbar; die lokalen Windows-Werte sind keine
  DSM-PSS-Werte.
- Der Worker-Peak bei einem echten großen Download kann über dem 256-MiB-Test
  liegen (TLS, curl_cffi, Netzwerkpuffer). Auf DSM messen.
- Kein DSM-Desktopfenster implementiert. Browseroberfläche bleibt aktiv;
  Klickschutz/CSP werden nicht gelockert. Siehe `docs/DSM_INTEGRATION.md`.
- Vorhandene unerwünschte NAS-Freigaben wurden hier nicht gelöscht: kein Zugriff
  auf das NAS. Update löscht keine Benutzerdaten. In DSM nur nach Inhaltsprüfung
  die ausdrücklich genannten Freigaben entfernen.

## Reproduktion

```bash
python tools/fetch_wheels.py
python tools/build_spk.py
python -m unittest discover -s tests
```

Erwartung: keine Testfehler und ein byte-identisches SPK bei gleichem
`SOURCE_DATE_EPOCH`. Browser-Test separat: `python tools/test_web_ui.py`
(optionale Entwicklerabhängigkeit Playwright mit installiertem Chromium).
