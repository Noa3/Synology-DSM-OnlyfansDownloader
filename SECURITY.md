# Sicherheit

## Melden

Sicherheitsprobleme bitte über die GitHub-Issues des Repositories melden:
<https://github.com/Noa3/Synology-DSM-OnlyfansDownloader/issues>

Bitte keine echten Sitzungscookies, HAR-Dateien oder Kontodaten in Issues
posten. Für reproduzierbare Fehler genügen synthetische Header und
Versionsangaben.

## Modell

- **Ein NAS-Benutzer** (Administrator) betreibt das Paket.
- Die Weboberfläche ist passwortgeschützt und für den Zugriff im vertrauenswürdigen
  LAN gedacht. Standard ist HTTP auf Port 8765; für externen Zugriff muss ein
  HTTPS-Reverse-Proxy davor.
- Der Steuerdienst läuft als eigener DSM-Dienstbenutzer `sc-onlyfansdl` und
  fordert **keine** root- oder Administratorgruppen-Rechte an.
- Keine `data-share`-Ressource: Installation und Start erstellen keine
  Benutzerfreigaben. Der Administrator erteilt `sc-onlyfansdl` ausschließlich
  auf der gewählten Freigabe Les-/Schreibrecht und bestätigt den Bibliothekspfad
  in der App. Vor dieser Bestätigung sind Downloads und Zeitplan gesperrt.
- Die OnlyFans-Sitzung wird ausschließlich lokal gespeichert
  (`var/data/session.json`, Modus `0600`). Sie wird nicht an Dritte gesendet und
  nicht in Einstellungen, Auftragsdaten oder Protokollen abgelegt.
- Die Anmeldung ist **kein DSM-SSO**. Das Web-Passwort ist unabhängig vom
  DSM-Benutzerkonto.

## Umgesetzte Schutzmaßnahmen

| Bereich | Maßnahme |
| --- | --- |
| Passwort | PBKDF2-HMAC-SHA256, 600.000 Iterationen, 16-Byte-Salt, `hmac.compare_digest` |
| Login | HttpOnly-Cookie, `SameSite=Strict`, 12 h Laufzeit, optional `Secure` |
| Brute Force | 5 Fehlversuche pro IP, 5-Minuten-Fenster, 60 s Sperre |
| CSRF | eigener Token pro Sitzung, Pflicht bei allen schreibenden Requests |
| Origin | fremder `Origin`/`Referer` wird abgelehnt |
| Sitzung | `session.json` 0600, atomisches Schreiben, keine Logs |
| Datenbank | `control.sqlite3` 0600, WAL, private Verzeichnisse 0700 |
| Pfade | Download-/Vorschau-Pfade müssen im erlaubten Ordner bleiben; Symlink-Prüfung |
| Dateinamen | `safe_component`/`safe_path` der bestehenden Engine |
| Worker | eigenes Environment, kein Netzzugriff auf Steuerdaten, Eltern-Watchdog |
| UI | statische Dateien, CSP ohne Inline-Skripte, keine externen Ressourcen |
| API | Größenlimits für JSON/Import, seitenweise Abfragen, begrenzte Ereignisse |

## Bewusste Grenzen

- **HTTP im LAN**: Ohne Reverse-Proxy sind Passwort und Cookie nicht durch TLS
  geschützt. Wer den Port 8765 ins Internet weiterleitet, gefährdet die Sitzung.
  Nutze DSM-Reverse-Proxy/HTTPS, eine Firewall und nach Möglichkeit
  `OFDL_COOKIE_SECURE=1` (Umgebungsvariable des Dienstes).
- **Dateizugriff**: Der Dienstbenutzer ist bewusst unprivilegiert. DSM-Rechte
  begrenzen seinen Dateizugriff; die App verwendet einen ausdrücklich
  gespeicherten Bibliothekspfad. Alte Freigaben und ACLs werden vom Update nicht
  gelöscht oder widerrufen. Nicht benötigte Freigaberechte in DSM entfernen.
- **Sitzungsimport**: Der eingefügte Text kann Cookies enthalten. Er wird im
  Browser verarbeitet und per HTTP an den lokalen Dienst gesendet. Keine
  HAR-Datei in einem geteilten Browser-Tab offen lassen. Die Dateiauswahl allein
  überträgt nichts; erst Importieren sendet den Inhalt. Exportdateien enthalten
  Zugangsdaten: nicht weitergeben und anschließend sicher löschen. Ein fremdes
  Login-Fenster wird nicht ausgelesen; CSP/Klickschutz bleiben aktiv.
- **Kein DRM-Bypass**: DRM-geschützte Medien werden gezählt und übersprungen.
  Es werden keine geschützten Inhalte entschlüsselt.
- **Keine Kaufautomatisierung**: Käufe und kostenpflichtige Aktionen sind nicht
  Teil der DSM-Oberfläche. Die bestehende Engine bleibt lesend.

## Passwort zurücksetzen

Wenn das Web-Passwort unbekannt ist:

1. Paket deinstallieren. Die Freigabe `OnlyFansDL` und alle Downloads bleiben
   erhalten; die privaten Steuerdaten werden entfernt.
2. Paket neu installieren und im Wizard ein neues Passwort setzen.
3. Im Download-Bereich denselben Bibliotheksordner auswählen.

Alternativ kann ein Administrator mit SSH die Datei
`/var/packages/OnlyFansDL/var/data/control.sqlite3` sichern, die Tabelle
`settings` bereinigen und den Dienst neu starten. Das ist nur ein
Diagnoseweg, kein regulärer Installationsschritt.

## Protokolle

- `var/logs/service.log` (rotierend, 2 MiB × 3)
- `var/logs/job-<id>.log` (stderr des Workers, 0600)

Die Protokolle enthalten keine Cookies, `x-bc`-Werte oder Sitzungstexte.
API-Fehlermeldungen sind bewusst sanitisiert. Bei unerwarteten Fehlern steht im
Auftragsprotokoll ein Python-Traceback; dieser kann lokale Pfade, aber keine
Sitzungswerte enthalten.
