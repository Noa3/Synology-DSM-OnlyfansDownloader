# OnlyFans DL für Synology DSM

Nativer Downloader für Synology DSM 7.2 – **ohne Docker, ohne Container Manager,
ohne SSH, ohne manuelle Python- oder pip-Befehle**. Das Paket bringt eine private
Python-Laufzeit mit, installiert alle benötigten Bibliotheken offline und startet
eine kleine Weboberfläche auf dem NAS.

> **Wichtig:** Dies ist ein inoffizieller Client. Verwende nur dein eigenes Konto
> und nur Inhalte, die du speichern darfst. Das Projekt umgeht keine Zugriffskontrollen,
> kein DRM und keine Sicherheitsabfragen. Die Live-API kann sich jederzeit ändern.

## Enthalten

- **Natives `.spk`** für DS723+ / DS923+ / DS1522+ (Architektur `r1000`, DSM 7.2).
- **Private Python-3.13-Umgebung** aus dem SynoCommunity-Paket `python313`.
  Die DSM-Systemumgebung bleibt unverändert.
- **Getrennter Steuerdienst und Worker**: Der Steuerdienst bleibt dauerhaft klein;
  Downloads, Abonnementscans und Vorschaubilder laufen in einem kurzlebigen
  Arbeitsprozess, der nach Erfolg, Fehler oder Abbruch beendet wird.
- **Weboberfläche** als statische Browseroberfläche: Anmeldung, Downloadordner,
  Creator-Auswahl, Kategorien/Filter, Downloadstart, Pause/Abbrechen, Zeitplan,
  Sitzungsimport, Sitzungstest, Status, Bibliotheksübersicht und Passwortänderung.
- **Bestehende Bibliotheken bleiben nutzbar**: Dateistruktur, `.part`-Dateien und
  das SQLite-Manifest `.ofdl.sqlite3` werden unverändert weiterverwendet.
- **Desktop-App und CLI bleiben im Quelltext erhalten**. Auf dem NAS wird die
  Weboberfläche verwendet; die Desktop-Tk-Oberfläche ist auf DSM nicht sinnvoll,
  weil dort kein Display/Tkinter vorhanden ist.
- **Reproduzierbarer Build** mit gepinnten Wheels und SHA-256-Hashes.

## Voraussetzungen

| Komponente | Anforderung |
| --- | --- |
| NAS | DS723+ (oder ein anderes Modell mit `r1000`), DSM 7.2 |
| Paketquelle | SynoCommunity: `https://packages.synocommunity.com/` |
| Laufzeit | SynoCommunity `python313` (3.13.11-9 oder neuer) – wird als Abhängigkeit installiert |
| Browser | aktueller Chrome, Edge, Firefox oder Safari im LAN |
| Speicher | ca. 100 MiB für Laufzeit/Wheels, plus Downloads |

Die Paketquelle ist nötig, weil Synology selbst kein Python 3.13 für DSM 7.2
bereitstellt. Die Installation der Laufzeit erfolgt über den Package Manager,
nicht über SSH.

## Installation

1. **SynoCommunity-Paketquelle hinzufügen** (einmalig):
   Package Center → Einstellungen → Paketquellen → Hinzufügen
   - Name: `SynoCommunity`
   - Ort: `https://packages.synocommunity.com/`
   - Die Quelle muss vertrauenswürdig sein; DSM zeigt ggf. einen Hinweis.
2. **`OnlyFansDL-r1000-dsm72_2.8.0-1.spk` herunterladen** (Release-Seite dieses
   Repositories) und in Package Center → Manuell installieren auswählen.
3. Package Center installiert **Python 3.13 automatisch** als Abhängigkeit.
   Falls die Laufzeit fehlt, zuerst `Python 3.13` aus SynoCommunity installieren.
4. Im Installationsdialog ein **Web-Passwort** (mindestens 10 Zeichen) festlegen.
   Es wird nur auf dem NAS gespeichert.
5. Nach der Installation **OnlyFans DL** im DSM-Hauptmenü öffnen oder
   `http://<NAS-IP>:8765/` aufrufen und mit dem Passwort anmelden.
6. Unter **Downloads** den Zielordner wählen. Standard ist
   `OnlyFansDL/OnlyFans` in der automatisch angelegten Freigabe `OnlyFansDL`.
   Ein bestehender Ordner (z. B. `/volume1/OnlyFans`) kann über **Durchsuchen**
   ausgewählt werden.
7. Unter **Sitzung** eine eingeloggte OnlyFans-API-Anfrage einfügen
   (cURL, HAR, JSON oder Roh-Header), **Importieren** und **Sitzung testen**.
8. Creator auswählen (manuell oder „Alle aktiven Abonnements“), Filter setzen und
   **Download starten**.

### Keine Kommandozeile nötig

Der normale Ablauf verwendet ausschließlich DSM Package Center und die
Weboberfläche. Python, pip, venv und die Wheels werden vom Paket installiert.
SSH ist nur für die optionale Speicher-/Diagnosemessung nötig (siehe
`docs/MEASUREMENT.md`), nicht für Installation oder Betrieb.

## Wo liegen die Daten?

| Daten | Ort |
| --- | --- |
| Downloads, `.part`, Manifest `.ofdl.sqlite3` | gewählter Ordner, z. B. `/volume1/OnlyFans` |
| Steuerdatenbank, Aufträge, Einstellungen | `/var/packages/OnlyFansDL/var/data/control.sqlite3` |
| Sitzung (0600) | `/var/packages/OnlyFansDL/var/data/session.json` |
| Python-Umgebung | `/var/packages/OnlyFansDL/var/venv` |
| Protokolle | `/var/packages/OnlyFansDL/var/logs/` |
| Vorschaubilder | `/var/packages/OnlyFansDL/var/data/previews/` |

Beim Deinstallieren werden die privaten Steuerdaten und die venv entfernt.
**Die Freigabe `OnlyFansDL` und alle Downloads bleiben erhalten.** Ein Update
behält Einstellungen, Sitzung und die venv bei und installiert nur geänderte
Wheels nach.

## Speicherverbrauch

Im Leerlauf läuft **nur** der Steuerdienst. Er importiert ausschließlich die
Python-Standardbibliothek; `requests`, `curl_cffi`, Pillow und der Download-Kern
werden erst im Worker geladen. Der Worker wird für jeden Auftrag neu gestartet
und beendet sich danach.

Gemessene lokale Vergleichswerte (Windows, nur als Indiz; **PSS ist dort nicht
verfügbar**):

| Zustand | Prozesse | RSS | Private |
| --- | --- | ---: | ---: |
| Steuerdienst nach Start | Dienst + venv-Launcher | ca. 33 MiB | ca. 18 MiB |
| Steuerdienst mit geöffneter Oberfläche | Dienst + Launcher | ca. 34 MiB | ca. 19 MiB |
| Streaming-Worker, 256 MiB Testdownload | Worker + Launcher | **Peak ca. 37 MiB** | ca. 28 MiB |

Auf DSM wird PSS mit `tools/measure_dsm.py` gemessen. Das vorläufige Ziel
**≤ 50 MiB PSS für alle eigenen Prozesse im Leerlauf** ist auf der DS723+ noch
zu bestätigen; es ist keine bereits zugesagte Garantie. Die Messsequenz und die
Bedingungen stehen in `docs/MEASUREMENT.md`.

## Reproduzierbarer Build

```bash
# 1) Wheels für CPython 3.13 / manylinux2014 x86_64 laden und hashen
python tools/fetch_wheels.py

# 2) SPK bauen (deterministisch; SOURCE_DATE_EPOCH ist fest)
python tools/build_spk.py

# Ergebnis
# dist/OnlyFansDL-r1000-dsm72_2.8.0-1.spk
# dist/OnlyFansDL-r1000-dsm72_2.8.0-1.spk.sha256
```

Der Build benötigt kein Docker, keinen Synology-Toolchain und kein Linux. Die
Wheels werden aus PyPI für die Zielplattform geladen und mit SHA-256 im Lockfile
festgehalten. Ein zweiter Build mit demselben `SOURCE_DATE_EPOCH` erzeugt auf
derselben Plattform byte-identische Dateien; der Inhalt (Quelltext, Lockfile,
Wheels) ist auch zwischen Windows und Linux identisch, die gzip-Komprimierung
kann sich jedoch zwischen zlib-Versionen unterscheiden. Der Release-Asset ist
der lokal geprüfte Windows-Build; CI baut zusätzlich ein inhaltsgleiches
Linux-Artefakt. `tests/test_dsm_package.py` prüft die Byte-Identität zweier
Builds auf derselben Plattform.

## Tests

```bash
python -m unittest discover -s tests -v
```

Die vollständige Suite umfasst die vorhandenen Desktop-/CLI-Tests und die neuen
DSM-Tests (Datenbank, Sicherheit, API, Worker, Paketaufbau). Ergebnisse und die
klare Trennung zwischen „lokal geprüft“ und „auf DSM-Hardware geprüft“ stehen in
`TEST_REPORT.md`.

## Sicherheit und Grenzen

- Die Oberfläche läuft standardmäßig über **HTTP auf Port 8765** im LAN. Für
  Zugriff von außen einen DSM-Reverse-Proxy mit HTTPS verwenden; die Anmeldung
  ist ein eigenes Passwort, keine DSM-SSO-Anmeldung.
- Die Sitzungsdatei ist `0600` und enthält nur die importierten Header/Cookies.
  Sie wird nicht in Einstellungen, Auftragsdaten oder Protokollen abgelegt.
- Das Paket läuft als eigener DSM-Dienstbenutzer `sc-onlyfansdl` und ist Mitglied
  der Gruppe `administrators`, damit der gewählte Downloadordner les- und
  schreibbar ist. Das ist für einen NAS-Downloader mit frei wählbarem Zielordner
  erforderlich; die Weboberfläche ist passwortgeschützt.
- Kein DRM-Bypass, keine Kaufautomatisierung, keine Umgehung von Cloudflare-
  oder sonstigen Sicherheitsabfragen.
- Die Live-API-Kompatibilität wurde in dieser Build-Umgebung **nicht** mit einem
  echten Konto getestet. Ein Sitzungstest auf dem NAS ist erforderlich.

## Lizenz

Der Anwendungskern und dieses Paket stehen unter der **GNU General Public
License v3** (siehe `LICENSE`). Die mitgelieferten Python-Wheels behalten ihre
jeweiligen Lizenzen; siehe `THIRD_PARTY_NOTICES.md`.

## Links

- Quelltext / Releases:
  <https://github.com/Noa3/Synology-DSM-OnlyfansDownloader>
- Ursprüngliche Desktop-Anwendung:
  <https://github.com/Noa3/onlyfans-dl-2>
- SynoCommunity:
  <https://synocommunity.com/>
