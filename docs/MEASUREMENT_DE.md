# Speicher messen (DS723+)

## Ziel und Einordnung

Vorläufiges Entwicklungsziel: **höchstens etwa 50 MiB PSS für alle eigenen
Prozesse zusammen im Leerlauf**. Das ist eine Zielmarke, keine bereits
zugesagte Garantie. Die tatsächlichen Werte müssen auf der DS723+ gemessen
werden.

PSS (Proportional Set Size) ist die faire Summe über Prozesse: gemeinsam
benutzte Seiten werden anteilig gezählt. RSS zählt gemeinsame Seiten in jedem
Prozess voll und ist deshalb als Summe zu hoch. Der Bericht nennt beide Werte,
die Zielmarke bezieht sich auf **PSS**.

## Werkzeug

`tools/measure_dsm.py` liest `/proc/<pid>/smaps_rollup` und `/proc/<pid>/status`.
Es benötigt nur die Python-Standardbibliothek und kann mit dem
SynoCommunity-Interpreter oder einem DSM-System-Python laufen:

```bash
# Einzelmessung
/var/packages/python313/target/bin/python3 \
  /volume1/OnlyFans/tools/measure_dsm.py snapshot --json

# 30 Sekunden sammeln, alle 2 Sekunden
/var/packages/python313/target/bin/python3 \
  /volume1/OnlyFans/tools/measure_dsm.py sample --seconds 30 --interval 2

# Aktive Arbeit: kurze Abtastung
/var/packages/python313/target/bin/python3 \
  /volume1/OnlyFans/tools/measure_dsm.py sample --seconds 20 --interval 0.5 --json
```

Das Skript findet Prozesse anhand der Kommandozeile:

- `ofdl.dsm.service` → Steuerdienst
- `ofdl.dsm.worker` → kurzfristiger Worker

Es zählt nur diese Prozesse, keine Browser, kein DSM und keine anderen Pakete.
Kopiere `tools/measure_dsm.py` dazu auf das NAS (z. B. per File Station in die
Freigabe) oder führe es aus dem entpackten Quelltext aus. Für den normalen
Betrieb ist das nicht nötig.

Alternativ liefert die Oberfläche unter **Übersicht → Dienst → Speicher**
bereits PSS/RSS des Steuerdienstes und des aktiven Workers (sofern `/proc`
verfügbar ist).

## Messbedingungen dokumentieren

Für jede Messung notieren:

- Datum/Uhrzeit, DSM-Version, Modell (DS723+), RAM-Ausstattung
- Anzahl laufender Pakete und ob der Browser geöffnet ist
- Bibliotheksgröße (Dateien, GiB) und Speichertyp (HDD/SSD/NVMe)
- ob ein Auftrag lief, welcher Typ und wie viele Dateien/Medien
- Netzwerk (LAN, Proxy, VPN) und Sitzungszustand
- Dauer der Leerlaufphase vor der Messung (mindestens 5 Minuten)

## Empfohlene Sequenz

1. **Nach dem Start**: Paket starten, 5 Minuten warten, keine Oberfläche öffnen.
   `sample --seconds 30 --interval 2` ausführen.
2. **Mit geöffneter Oberfläche**: Browser auf der Übersicht, 2 Minuten warten,
   dann 30 Sekunden messen. Zusätzlich `tools/dsm_http_check.py --open-ui`
   ausführen, um alle UI-Ressourcen einmal zu laden.
3. **Großer Auftrag**: „Alle aktiven Abonnements“, alle Kategorien und Typen,
   vorhandene Bibliothek. Während des Laufs 20–60 Sekunden mit
   `--interval 0.5` messen. Spitzenwerte notieren.
4. **Abbruch**: Auftrag abbrechen, 30 Sekunden warten (Worker muss beendet sein),
   erneut im Leerlauf messen.
5. **Mehrere Durchläufe**: Sequenz 2–4 dreimal wiederholen. Prüfen, ob PSS/RSS
   nach jedem Lauf zum Ausgangswert zurückkehrt.
6. **Update/Neustart**: NAS neu starten, nach dem Start erneut messen.
   Sicherstellen, dass keine verwaisten Worker-Prozesse übrig bleiben
   (`ps`/`measure_dsm.py` zeigt nur einen Dienst, keinen Worker im Leerlauf).

## Ergebnistabelle (auf dem NAS auszufüllen)

| Zustand | Prozesse | PSS gesamt (MiB) | RSS gesamt (MiB) | Spitze Worker (MiB) | Bedingungen |
| --- | ---: | ---: | ---: | ---: | --- |
| Nach Start, 5 min idle |  |  |  | – |  |
| Oberfläche offen, 2 min |  |  |  | – |  |
| Großer Auftrag läuft |  |  |  |  |  |
| Nach Abbruch, 30 s |  |  |  | – |  |
| Nach 3 Durchläufen |  |  |  | – |  |
| Nach NAS-Neustart |  |  |  | – |  |

## Lokale Vergleichsmessung (nicht DSM)

Diese Werte wurden in der Build-Umgebung unter Windows gemessen. Sie sind
**kein DSM-Nachweis**; PSS ist unter Windows nicht verfügbar. Der
venv-Launcher ist ein zusätzlicher kleiner Prozess, den es unter Linux nicht
gibt.

| Zustand | Prozesse | RSS | Private |
| --- | --- | ---: | ---: |
| Steuerdienst nach Start | Dienst + Launcher | 33,0 MiB | 18,5 MiB |
| Steuerdienst, UI-Ressourcen geladen | Dienst + Launcher | 33,6 MiB | 18,9 MiB |
| Nach 5 Vorschau-Aufträgen | Dienst + Launcher | 33,9 MiB | 19,0 MiB |
| Streaming-Worker, 256 MiB Testdownload | Worker + Launcher | **37,3 MiB Peak** | 28,2 MiB |
| Import-Baseline Download-Worker | Worker + Launcher | 39,6 MiB | 28,0 MiB |
| Import-Baseline Preview-Worker | Worker + Launcher | 26,0 MiB | 14,3 MiB |

Der 256-MiB-Test verwendet den echten `run_downloads`-Pfad mit Manifest,
Byte-Range-/Längenprüfung, 256-KiB-Chunks und einer lokalen HTTP-Quelle; nur die
Host-/Portprüfung wurde für die lokale Messung gelockert. Der Peak zeigt, dass
die Streaming-Engine die Datei nicht in den Speicher lädt.

## Was die Zahlen nicht aussagen

- Ein einzelner Peak sagt nichts über Langzeitstabilität bei 80.000 Dateien.
- Der LegacyIndex kann beim ersten Lauf für einen Creator zusätzlichen Speicher
  benötigen, wenn exakte Pfade fehlen. Das ist ein Worker-Spitzenwert, kein
  Dauerzustand; der Worker endet nach dem Auftrag.
- Die tatsächliche Netzwerkgeschwindigkeit, TLS-Impersonation und
  Cloudflare-Antworten können die Laufzeit, nicht den Grundspeicherbedarf,
  verändern.
- Ohne echte Sitzung kann kein echter Mediendownload gemessen werden. Der
  Testbericht kennzeichnet diese Lücke ausdrücklich.
