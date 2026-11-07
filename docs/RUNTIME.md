# Runtime and dependencies

## Available SynoCommunity packages (verified)

Build state: 2026-11-07, package source `https://packages.synocommunity.com/`
and `SynoCommunity/spksrc` (master).

| Package | Published | Architecture `r1000` | DSM minimum | Contents |
| --- | --- | --- | --- | --- |
| `python313` | 3.13.11-9 | yes | 7.1-42661 | Python 3.13, venv, ensurepip (pip 25.3) |
| `python314` | 3.14.7-5 | yes | 7.1-42661 | Python 3.14, venv, ensurepip |

`spksrc` master already contains `python313` 3.13.14-11 and `python314`
3.14.7-5. Installation uses the published package from the package source, so
the dependency is declared as `python313>=3.13.11-9`.

The DS723+ is assigned to architecture **`r1000`** (AMD Ryzen R1600, DSM 7.2).
The package declares `arch="r1000"` and `os_min_ver="7.2-64570"`.

## Comparison with application dependencies

The application core requires:

| Dependency | Purpose | Python 3.13 | Python 3.14 |
| --- | --- | --- | --- |
| `requests` | HTTP, API, rules | pure Python | pure Python |
| `PySocks` | SOCKS proxy | pure Python | pure Python |
| `m3u8` | optional HLS recording | pure Python | pure Python |
| `Pillow` | preview images | `cp313` wheel | `cp314` wheel from 12.2 |
| `curl_cffi` | browser-like TLS | `cp310-abi3` wheel | `cp310-abi3` wheel |

Both runtimes would be technically possible. **Python 3.13 was chosen** because:

1. The existing test suite runs on CPython 3.13 in this environment (desktop
   test report: 3.13.5; here: 3.13.12).
2. Tested `manylinux2014` wheels for `cp313` exist for all binary packages.
3. The published SynoCommunity package 3.13.11-9 demonstrably contains
   `lib/python3.13/venv` and `ensurepip` with a pip wheel. This allows creating
   the private environment without network access and without changing the
   system.
4. Python 3.14 would require its own wheel set and a full new test run; that is
   deliberately not declared as “tested”.

## Private environment

The installer uses exclusively the SynoCommunity package interpreter:

```
/var/packages/python313/target/bin/python3
```

and creates the environment under

```
/var/packages/OnlyFansDL/var/venv
```

The DSM system interpreter and its `site-packages` are not modified. The venv is
created with `python3 -m venv`; if that fails, `python3 -m virtualenv` is tried.
The wheels are then installed **offline**:

```bash
"$VENV/bin/python" -m pip install \
  --no-index --find-links "$PKGDEST/wheelhouse" \
  --require-hashes --no-cache-dir \
  -r "$PKGDEST/requirements-dsm.lock"
```

`requirements-dsm.lock` contains all direct and transitive dependencies with
SHA-256 hashes. The build verifies the hashes before packaging.

## Bundled wheels (22.1 MiB)

| Wheel | Size |
| --- | ---: |
| `curl_cffi-0.17.0-cp310-abi3-manylinux2014_x86_64` | 13.40 MiB |
| `pillow-12.2.0-cp313-cp313-manylinux2014_x86_64` | 7.72 MiB |
| `charset_normalizer-3.5.2-cp313-cp313-manylinux2014_x86_64` | 0.24 MiB |
| `cffi-2.1.1-cp313-cp313-manylinux2014_x86_64` | 0.21 MiB |
| `certifi-2026.10.23-py3-none-any` | 0.13 MiB |
| `urllib3-2.8.0-py3-none-any` | 0.13 MiB |
| `idna-3.20-py3-none-any` | 0.07 MiB |
| `requests-2.34.2-py3-none-any` | 0.07 MiB |
| `pycparser-3.12-py3-none-any` | 0.06 MiB |
| `m3u8-6.0.0-py3-none-any` | 0.02 MiB |
| `PySocks-1.7.1-py3-none-any` | 0.02 MiB |

`keyring` and `playwright` are **not** part of the DSM runtime. The web
interface does not need them; the session is entered via the existing import
mechanism. The desktop app and CLI remain in the source and continue to use
`requirements.txt` outside DSM.

## glibc / manylinux

DSM 7.2 provides glibc 2.36 (DSM 7.0/7.1: 2.26). All binary wheels are
`manylinux2014`/`manylinux_2_17` and thus run on DSM 7.2. The package requires
DSM 7.2 to keep the tested glibc base and the SynoCommunity state unambiguous.
`curl_cffi` bundles its libcurl dependencies in the wheel; no system `libcurl`
is required.

## What does not run on the NAS

- The Tk desktop UI (`ofdl/ui.py`) needs Tkinter and a display. The
  SynoCommunity Python package does not provide Tkinter; on a NAS without a
  display the Tk UI is therefore not the intended path.
- Playwright/Chromium is not installed. The desktop app's browser login is not
  available on DSM; session import is the intended path.
- `ffmpeg` is optional. Without ffmpeg the preview for videos returns a
  placeholder; downloads and live recording (m3u8) work independently.
