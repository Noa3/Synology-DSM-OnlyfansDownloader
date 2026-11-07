# Laufzeit und Abhängigkeiten

## Verfügbare SynoCommunity-Pakete (geprüft)

Stand des Builds: 2026-11-07, Paketquelle `https://packages.synocommunity.com/`
und `SynoCommunity/spksrc` (master).

| Paket | Veröffentlicht | Architektur `r1000` | DSM-Minimum | Inhalt |
| --- | --- | --- | --- | --- |
| `python313` | 3.13.11-9 | ja | 7.1-42661 | Python 3.13, venv, ensurepip (pip 25.3) |
| `python314` | 3.14.7-5 | ja | 7.1-42661 | Python 3.14, venv, ensurepip |

`spksrc` master enthält bereits `python313` 3.13.14-11 und `python314`
3.14.7-5. Für die Installation zählt das veröffentlichte Paket der Paketquelle;
die Abhängigkeit ist deshalb als `python313>=3.13.11-9` deklariert.

Die DS723+ ist der Architektur **`r1000`** zugeordnet (AMD Ryzen R1600, DSM 7.2).
Das Paket deklariert `arch="r1000"` und `os_min_ver="7.2-64570"`.

## Abgleich mit den Anwendungsabhängigkeiten

Der Anwendungskern benötigt:

| Abhängigkeit | Zweck | Python 3.13 | Python 3.14 |
| --- | --- | --- | --- |
| `requests` | HTTP, API, Regeln | pure Python | pure Python |
| `PySocks` | SOCKS-Proxy | pure Python | pure Python |
| `m3u8` | optionale HLS-Aufzeichnung | pure Python | pure Python |
| `Pillow` | Vorschaubilder | `cp313`-Wheel | `cp314`-Wheel ab 12.2 |
| `curl_cffi` | browserähnliches TLS | `cp310-abi3`-Wheel | `cp310-abi3`-Wheel |

Beide Laufzeiten wären technisch möglich. **Gewählt wurde Python 3.13**, weil:

1. Die vorhandene Testsuite in dieser Umgebung auf CPython 3.13 ausgeführt wird
   (Desktop-Testbericht: 3.13.5; hier: 3.13.12).
2. Für alle Binärpakete liegen getestete `manylinux2014`-Wheels für `cp313` vor.
3. Das veröffentlichte SynoCommunity-Paket 3.13.11-9 enthält nachweislich
   `lib/python3.13/venv` und `ensurepip` mit einem pip-Wheel. Damit kann die
   private Umgebung ohne Netzwerk und ohne Systemänderung erstellt werden.
4. Python 3.14 würde einen eigenen Wheel-Satz und einen erneuten vollständigen
   Testlauf erfordern; das ist bewusst nicht als „getestet“ deklariert.

## Private Umgebung

Der Installer verwendet ausschließlich den Interpreter des SynoCommunity-Pakets:

```
/var/packages/python313/target/bin/python3
```

und legt die Umgebung unter

```
/var/packages/OnlyFansDL/var/venv
```

an. Der DSM-Systeminterpreter und dessen `site-packages` werden nicht verändert.
Die venv wird mit `python3 -m venv` erstellt; schlägt das fehl, wird
`python3 -m virtualenv` versucht. Anschließend werden die Wheels **offline**
installiert:

```bash
"$VENV/bin/python" -m pip install \
  --no-index --find-links "$PKGDEST/wheelhouse" \
  --require-hashes --no-cache-dir \
  -r "$PKGDEST/requirements-dsm.lock"
```

`requirements-dsm.lock` enthält alle direkten und transitiven Abhängigkeiten mit
SHA-256-Hashes. Der Build prüft die Hashes vor dem Packen.

## Enthaltene Wheels (22,1 MiB)

| Wheel | Größe |
| --- | ---: |
| `curl_cffi-0.17.0-cp310-abi3-manylinux2014_x86_64` | 13,40 MiB |
| `pillow-12.2.0-cp313-cp313-manylinux2014_x86_64` | 7,72 MiB |
| `charset_normalizer-3.5.2-cp313-cp313-manylinux2014_x86_64` | 0,24 MiB |
| `cffi-2.1.1-cp313-cp313-manylinux2014_x86_64` | 0,21 MiB |
| `certifi-2026.10.23-py3-none-any` | 0,13 MiB |
| `urllib3-2.8.0-py3-none-any` | 0,13 MiB |
| `idna-3.20-py3-none-any` | 0,07 MiB |
| `requests-2.34.2-py3-none-any` | 0,07 MiB |
| `pycparser-3.12-py3-none-any` | 0,06 MiB |
| `m3u8-6.0.0-py3-none-any` | 0,02 MiB |
| `PySocks-1.7.1-py3-none-any` | 0,02 MiB |

`keyring` und `playwright` sind **nicht** Teil der DSM-Laufzeit. Die
Weboberfläche benötigt sie nicht; die Sitzung wird über den vorhandenen
Importmechanismus eingegeben. Die Desktop-App und die CLI bleiben im Quelltext
erhalten und verwenden außerhalb von DSM weiterhin `requirements.txt`.

## glibc / manylinux

DSM 7.2 liefert glibc 2.36 (DSM 7.0/7.1: 2.26). Alle Binärwheels sind
`manylinux2014`/`manylinux_2_17` und damit auf DSM 7.2 lauffähig. Das Paket
verlangt DSM 7.2, um die getestete glibc-Basis und den SynoCommunity-Stand
eindeutig zu halten. `curl_cffi` bringt seine libcurl-Abhängigkeiten im Wheel
mit; es ist kein System-`libcurl` nötig.

## Was auf dem NAS nicht läuft

- Die Tk-Desktopoberfläche (`ofdl/ui.py`) benötigt Tkinter und ein Display. Das
  SynoCommunity-Python-Paket liefert kein Tkinter; auf einem NAS ohne Display ist
  die Tk-Oberfläche daher nicht der vorgesehene Weg.
- Playwright/Chromium ist nicht installiert. Der Browser-Login der Desktop-App
  ist auf DSM nicht verfügbar; der Sitzungsimport ist der vorgesehene Weg.
- `ffmpeg` ist optional. Ohne ffmpeg liefert die Vorschau für Videos einen
  Platzhalter; Downloads und Live-Aufzeichnung (m3u8) funktionieren unabhängig
  davon.
