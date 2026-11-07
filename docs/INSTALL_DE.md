# Installation auf DSM 7.2 (DS723+)

Diese Anleitung beschreibt den vollständigen Weg über die DSM-Oberfläche.
Für Installation, Einrichtung und Betrieb sind **keine SSH-, Python- oder
pip-Befehle** erforderlich.

## 1. SynoCommunity-Paketquelle hinzufügen

1. DSM öffnen → **Package Center**.
2. **Einstellungen** → **Paketquellen** → **Hinzufügen**.
3. Name: `SynoCommunity`
4. Ort: `https://packages.synocommunity.com/`
5. Speichern. Die Quelle wird für die Python-3.13-Laufzeit benötigt, weil
   Synology selbst kein Python 3.13 für DSM 7.2 bereitstellt.

## 2. Paket installieren

1. Die Datei `OnlyFansDL-r1000-dsm72_2.8.0-2.spk` aus dem Release herunterladen.
2. Package Center → **Manuell installieren** → Datei auswählen.
3. DSM zeigt die Abhängigkeit **Python 3.13** an und installiert sie
   automatisch aus der SynoCommunity-Quelle.
4. Im Installationsdialog das **Web-Passwort** (mindestens 10 Zeichen) zweimal
   eingeben. Es gilt nur für die OnlyFans-DL-Oberfläche, nicht für DSM.
5. Installation abschließen.

Falls die Installation mit „Python 3.13 nicht gefunden“ abbricht:

- Prüfen, ob die SynoCommunity-Quelle korrekt ist.
- `Python 3.13` im Package Center suchen und zuerst installieren.
- Danach das OnlyFans-DL-Paket erneut installieren.

## 3. Oberfläche öffnen

Nach der Installation erscheint **OnlyFans DL** im DSM-Hauptmenü. Alternativ im
Package Center auf **Öffnen** klicken oder direkt aufrufen:

```
http://<NAS-IP>:8765/
```

Die Oberfläche läuft auf Port **8765**. Wenn der Port belegt ist, meldet DSM
beim Installieren einen Portkonflikt; in diesem Fall den belegenden Dienst
ändern (der Port ist im Paket fest eingestellt).

Anmelden mit dem im Wizard gesetzten Passwort.

## 4. Downloadordner auswählen

1. Reiter **Downloads** → **Durchsuchen**.
2. Standardmäßig werden die Freigaben **OnlyFansDL** und **OnlyFans** für das
   Dienstkonto vorbereitet. Der Unterordner `OnlyFansDL/OnlyFans` ist
   voreingestellt. Eine bereits vorhandene Freigabe `OnlyFans` kann direkt als
   bestehende Bibliothek ausgewählt werden.
3. Für eine andere bestehende Bibliothek zum gewünschten Ordner navigieren.
   Das Dienstkonto ist unprivilegiert und benötigt dort Les-/Schreibrecht;
   andernfalls zeigt der Dialog einen Berechtigungsfehler. Alternativ die
   Bibliothek in `OnlyFansDL` oder `OnlyFans` verschieben/kopieren.
4. Ein bestehender Ordner wird nicht umbenannt oder geleert; `.ofdl.sqlite3`,
   `.part`-Dateien und die vorhandene Struktur bleiben unverändert.

Neue Unterordner können direkt im Dialog mit **Anlegen** erstellt werden.

## 5. OnlyFans-Sitzung importieren

1. Im eingeloggten Browser auf `onlyfans.com` eine Anfrage an
   `https://onlyfans.com/api2/v2/...` kopieren:
   - Chrome/Edge: Entwicklerwerkzeuge → Netzwerk → Anfrage → **Copy as cURL (bash)**
   - oder HAR/JSON/Header aus einem API-Request.
2. In der OnlyFans-DL-Oberfläche → **Sitzung** den Text einfügen.
3. **Importieren** klicken. Die Oberfläche zeigt die Konto-ID.
4. **Sitzung testen** klicken. Erst nach erfolgreichem Test zeigt der Status
   **Verbunden**. Der Test ist ein eigener Worker-Auftrag und beendet sich
   danach.
5. Bei Fehlern: frische Anfrage aus dem normalen Browser kopieren, gleiche
   Netzwerkverbindung verwenden, Uhrzeit des NAS prüfen.

Die Sitzung wird unter
`/var/packages/OnlyFansDL/var/data/session.json` mit Dateirechten `0600`
gespeichert. Sie erscheint nicht in Einstellungen, Auftragsdaten oder
Protokollen.

## 6. Creator und Download

- **Alle aktiven Abonnements** aktivieren, oder
- **Abonnements laden** und einzelne Creator ankreuzen, oder
- Namen/Profil-URLs manuell eingeben.
- Kategorien (Posts, Archiviert, Stories, Nachrichten, Gekauft), Dateitypen
  (Fotos, Videos, Audio) und Optionen (Alben, Kategorie-Unterordner, Vorschau)
  auswählen.
- **Download starten**.
- Unter **Übersicht** laufen Fortschritt, Statistik und Ereignisse. **Pause**
  hält den Auftrag an; **Abbrechen** beendet ihn, fertige Dateien bleiben
  erhalten.
- **Nur suchen (Scan)** schreibt kein Medium, sondern zeigt die geplanten
  Dateien im Ereignisprotokoll.

Es läuft immer höchstens ein Auftrag. Ein zweiter Start wird mit einem Hinweis
abgelehnt.

## 7. Zeitplan

Reiter **Einstellungen**:

- **Täglicher Download automatisch starten** aktivieren.
- Uhrzeit in NAS-Zeit wählen.
- **Zeitplan speichern**.

Der Zeitplan verwendet die zuletzt gespeicherten Download-Einstellungen. Ein
verpasster Lauf wird am selben Tag nachgeholt, wenn der Dienst läuft. Ohne
Sitzung oder bei laufendem Auftrag wird nicht gestartet.

## 8. Bibliothek und Manifest

Reiter **Bibliothek** zeigt:

- den gewählten Ordner,
- ob `.ofdl.sqlite3` vorhanden ist,
- Anzahl und Größe der manifestierten Dateien,
- freien Speicher.

Die Zahlen kommen aus dem Manifest, nicht aus einem vollständigen Dateiscan.
Bei rund 80.000 Dateien bleibt die Oberfläche dadurch schnell und
speicherschonend. Der erste Lauf nach einer Übernahme kann länger dauern, weil
die Engine alte Layouts einmalig prüft; spätere Läufe nutzen exakte Pfade und
das Manifest.

## 9. Update

1. Neue `.spk` aus dem Release herunterladen.
2. Package Center → Manuell installieren.
3. DSM erkennt das Upgrade. Einstellungen, Sitzung, venv und Downloads bleiben
   erhalten; die Wheels werden bei Bedarf nachinstalliert.
4. Das Web-Passwort bleibt unverändert.

## 10. Deinstallation

Package Center → OnlyFans DL → Deinstallieren.

Entfernt werden die privaten Steuerdaten, die venv und die Protokolle.
**Nicht** entfernt werden die Freigaben `OnlyFansDL`/`OnlyFans` und alle
heruntergeladenen Dateien. Ein späteres Neuinstallieren findet die Bibliothek
wieder, wenn derselbe Ordner ausgewählt wird.

## Fehlerbehebung

| Symptom | Ursache / Lösung |
| --- | --- |
| „Python 3.13 wurde nicht gefunden“ | SynoCommunity-Quelle fehlt oder `python313` ist nicht installiert. Quelle prüfen, Python 3.13 installieren, Paket erneut installieren. |
| Paket startet nicht | Package Center → Protokoll ansehen; zusätzlich `/var/packages/OnlyFansDL/var/logs/service.log` (nur mit SSH/File Station lesbar). Häufig: Port 8765 belegt. |
| Anmeldung funktioniert nicht | Passwort aus dem Installations-Wizard verwenden. Bei vergessenem Passwort Paket deinstallieren und neu installieren (Downloads bleiben erhalten) oder die Steuerdaten zurücksetzen. |
| „Keine Sitzung eingerichtet“ | Unter **Sitzung** importieren und testen. |
| Sitzungstest schlägt fehl | Anfrage von `onlyfans.com/api2/v2/` kopieren, nicht von einer anderen Seite. Session kann an Netz/IP gebunden sein; im gleichen Netz wie der Browser testen. Cloudflare-Anfragen werden nicht umgangen. |
| „Paket benötigt root-Rechte“ / Administratorwarnung | Es wird die alte Version 2.8.0-1 installiert. Version **2.8.0-2** verwenden; sie fordert keine root-/Administratorgruppen-Rechte an. |
| Downloadordner nicht beschreibbar | Einen Ordner unter `OnlyFansDL` oder `OnlyFans` wählen. Andere Freigaben benötigen eine Freigabeberechtigung für `sc-onlyfansdl`; das Paket fordert bewusst keine Administratorgruppe an. |
| Kein DSM-Menüeintrag | Paket neu starten; `reloadui` wird beim Installieren gesetzt. Alternativ `http://<NAS-IP>:8765/` direkt öffnen. |
| Viele Dateien, langsamer erster Lauf | Erwartet bei Altlayouts; Folgeläufe nutzen das Manifest. Keine Medien werden dauerhaft im Steuerdienst gehalten. |

## Sicherheitshinweis

Die Oberfläche ist für den Zugriff im vertrauenswürdigen LAN gedacht. Für
Zugriff über das Internet einen DSM-Reverse-Proxy mit HTTPS verwenden und Port
8765 nicht direkt freigeben. Das Web-Passwort ist eine eigene Anmeldung, keine
DSM-SSO-Anmeldung.
