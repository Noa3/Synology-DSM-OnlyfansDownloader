# OnlyFans DL for Synology DSM

**English** · [Deutsch](README_DE.md) · [GitHub Pages](https://noa3.github.io/Synology-DSM-OnlyfansDownloader/)

A native downloader for Synology DSM 7.2 – **no SSH and no manual Python or pip
commands**. The package ships a private Python runtime, installs all required
libraries offline and starts a small web interface on the NAS.

> **Important:** This is an unofficial client. Use only your own account and
> only content you are allowed to save. The project does not bypass access
> controls, DRM or security challenges. The live API may change at any time.

<img width="1767" height="1437" alt="OnlyFans DL DSM screenshot" src="https://github.com/user-attachments/assets/615aa274-fa2a-41da-9f01-10cfc64c7333" />

## Contents

- **Native `.spk`** for DS723+ / DS923+ / DS1522+ (`r1000` architecture, DSM 7.2).
- **Private Python 3.13 environment** from the SynoCommunity `python313`
  package. The DSM system environment remains untouched.
- **Separate control service and worker**: the control service stays small
  permanently; downloads, subscription scans and previews run in a short-lived
  worker process that exits after success, failure or cancellation.
- **Web interface** as a static browser UI: login, download folder, creator
  selection, categories/filters, starting downloads, pause/cancel, schedule,
  session import, session test, status, library overview and password change.
- **Existing libraries remain usable**: file structure, `.part` files and the
  `.ofdl.sqlite3` SQLite manifest are reused unchanged.
- **Desktop app and CLI remain in the source**. On the NAS the web interface is
  used; the Tk desktop UI is not suitable there because DSM has no display or
  Tkinter.
- **Reproducible build** with pinned wheels and SHA-256 hashes.

## Requirements

| Component | Requirement |
| --- | --- |
| NAS | DS723+ (or another model with `r1000`), DSM 7.2 |
| Package source | SynoCommunity: `https://packages.synocommunity.com/` |
| Runtime | SynoCommunity `python313` (3.13.11-9 or newer) – installed as a dependency |
| Browser | current Chrome, Edge, Firefox or Safari on the LAN |
| Storage | about 100 MiB for runtime/wheels, plus downloads |

The package source is required because Synology itself does not provide Python
3.13 for DSM 7.2. The runtime is installed through Package Center, not SSH.

## Installation

1. **Add the SynoCommunity package source** (one time):
   Package Center → Settings → Package Sources → Add
   - Name: `SynoCommunity`
   - Location: `https://packages.synocommunity.com/`
   - The source must be trusted; DSM may show a notice.
2. **Download `OnlyFansDL-r1000-dsm72_2.8.0-9.spk`** (from this repository's
   releases) and choose Package Center → Manual Install.
3. Package Center installs **Python 3.13 automatically** as a dependency. If the
   runtime is missing, install `Python 3.13` from SynoCommunity first.
4. In the install wizard, set a **web password** (at least 10 characters). It is
   stored only on the NAS.
5. After installation, open **OnlyFans DL** from the DSM main menu or visit
   `http://<NAS-IP>:8765/` and sign in with that password.
6. In DSM, open **Control Panel → Shared Folder → the desired share → Edit →
   Permissions → System internal user** and grant `sc-onlyfansdl`
   **Read/Write**. Then in the app open **Settings → Library path**, choose an
   existing folder and **Save path**. Downloads, library and schedule use this
   path. **No shared folders are created or granted automatically.** After an
   upgrade from 2.8.0-3 the path must be confirmed once.
7. Under **Session**, paste a request from your logged-in OnlyFans browser
   (cURL, HAR, JSON or raw headers), click **Import**, then **Test session**.
8. Select creators (manually or “All active subscriptions”), choose filters and
   click **Start download**.

### No command line required

Normal use relies only on DSM Package Center and the web interface. Python, pip,
venv and the wheels are installed by the package. SSH is needed only for the
optional memory/diagnostics measurement (see `docs/MEASUREMENT.md`), not for
installation or operation.

## Languages

- **Web interface:** German, English, French, Spanish, plus Italian, Dutch and
  Portuguese core texts. Untranslated help/technical text falls back to
  English or German.
- **Auto · DSM / Browser:** uses a supported DSM language hint or readable
  language cookie, otherwise the readable DSM system language, otherwise the
  browser. The individual DSM user language is not always available to a
  standalone window. A manual choice overrides Auto and is stored in the browser.
- **GitHub Pages:** English (default), German, French, Spanish, Italian, Dutch
  and Portuguese.
- **Documentation:** English is the default. German versions are available as
  `*_DE.md`.

## Where is the data?

| Data | Location |
| --- | --- |
| Downloads, `.part`, manifest `.ofdl.sqlite3` | chosen folder, e.g. `/volume1/OnlyFans` |
| Control database, jobs, settings | `/var/packages/OnlyFansDL/var/data/control.sqlite3` |
| Session (0600) | `/var/packages/OnlyFansDL/var/data/session.json` |
| Python environment | `/var/packages/OnlyFansDL/var/venv` |
| Logs | `/var/packages/OnlyFansDL/var/logs/` |
| Previews | `/var/packages/OnlyFansDL/var/data/previews/` |
| Private upgrade/daily snapshots (last 5) | `/var/packages/OnlyFansDL/var/backups/` |

Uninstalling removes the private control data, the venv and the snapshots.
**Chosen libraries and all downloads remain.** An update keeps settings, session
and venv and only installs changed wheels.

Before an upgrade the package snapshots `control.sqlite3` (web password, library
path, schedule, proxy, free-resubscribe settings, download defaults), the
imported `session.json` and free-resubscribe history. The new version restores a
snapshot only if the live database or session is missing or corrupt; valid data
is never overwritten. A failed restore stops the upgrade rather than starting
empty. A daily snapshot is also kept while the service runs. The last five
snapshots stay under `var/backups` with private permissions.

## Sessions, status and Free & Trials

- The OnlyFans session remains in `var/data/session.json` (0600, not encrypted)
  across page reloads, package restarts and upgrades. OnlyFans can revoke or
  expire it; it is not renewed automatically. The separate web login expires
  after 12 hours or when the service restarts.
- The active/latest job and recent events are restored after a reload.
  Connection problems do not clear the display and do not start a second job.
- While scanning, the total size is unknown; overall progress and current-file
  progress use separate bars. Full errors are visible in the job card.
- Temporary API read failures on DSM wait at least 180 seconds before the next
  attempt; a longer `Retry-After` is honored up to 300 seconds, above that the
  run stops. 401/authentication failures need a fresh session; security
  challenges are not bypassed. No automatic POST retries.
- **Free & Trials:** discover offers read-only. Only explicitly listed profiles
  that are immediately rechecked as permanently free can be subscribed
  automatically. The daily automation is off by default and account-bound.
  Trials remain for review on the website because later fees are possible.
  A price change between check and server response cannot be made atomic.
- **DSM Stop:** owned worker process groups including children are terminated;
  PID identity is checked and a missing service PID file can be reconstructed.
  Linux process tests and the pending DSM test are separate.

Details: [`docs/RELIABILITY.md`](docs/RELIABILITY.md).

## Memory usage

At idle **only** the control service runs. It imports only the Python standard
library; `requests`, `curl_cffi`, Pillow and the download core are loaded only in
the worker. The worker is restarted for each job and exits afterwards.

Measured local reference values (Windows, indicative only; **PSS is not available
there**):

| State | Processes | RSS | Private |
| --- | --- | ---: | ---: |
| Control service after start | service + venv launcher | approx. 33 MiB | approx. 18 MiB |
| Control service with UI open | service + launcher | approx. 34 MiB | approx. 19 MiB |
| Streaming worker, 256 MiB test download | worker + launcher | **peak approx. 37 MiB** | approx. 28 MiB |

On DSM, PSS is measured with `tools/measure_dsm.py`. The provisional target
**≤ 50 MiB PSS for all own processes at idle** still has to be confirmed on the
DS723+; it is not a guaranteed promise. The measurement sequence and conditions
are in `docs/MEASUREMENT.md`.

## Reproducible build

```bash
# 1) Download and hash wheels for CPython 3.13 / manylinux2014 x86_64
python tools/fetch_wheels.py

# 2) Build the SPK (deterministic; SOURCE_DATE_EPOCH is fixed)
python tools/build_spk.py

# Result
# dist/OnlyFansDL-r1000-dsm72_2.8.0-9.spk
# dist/OnlyFansDL-r1000-dsm72_2.8.0-9.spk.sha256
```

The build needs no Synology toolchain and no Linux. Wheels are downloaded from
PyPI for the target platform and pinned with SHA-256 in the lock file. A second
build with the same `SOURCE_DATE_EPOCH` produces byte-identical files on the
same platform; content (source, lock file, wheels) is identical between Windows
and Linux, although gzip compression can differ between zlib versions. The
release asset is the locally tested Windows build; CI additionally builds a
content-identical Linux artifact. `tests/test_dsm_package.py` checks byte
identity of two builds on the same platform.

## Tests

```bash
python -m unittest discover -s tests -v
```

The full suite covers the existing desktop/CLI tests and the DSM tests (database,
security, API, worker, package layout). Results and the clear distinction between
“tested locally” and “tested on DSM hardware” are in `TEST_REPORT.md`.

## Security and limits

- The interface runs over **HTTP on port 8765** on the LAN by default. For
  external access use a DSM reverse proxy with HTTPS; the login is its own
  password, not DSM single sign-on.
- The session file is `0600` and contains only imported headers/cookies. It is
  not stored in settings, job data or logs. File permissions do not protect it
  from NAS administrators/root or a compromised NAS.
- The package runs as its own DSM service user `sc-onlyfansdl` and requests
  **no** root or administrator group rights. The user grants only the chosen
  share to this account; otherwise the interface reports a permission error.
  Old automatically created shares are not deleted and are not used without a
  new path confirmation.
- No DRM bypass, no purchase automation, no bypass of Cloudflare or other
  security challenges.
- Live API compatibility was **not** tested with a real account in this build
  environment. A session test on the NAS is required.

## DSM window and simplified login

A window inside the DSM desktop is generally possible but needs an HTTPS /
same-origin integration. Simple embedding of HTTP port 8765 would fail on
HTTPS DSM due to mixed content and click protection. **2.8.0-9 still opens the
browser interface**; security headers are not disabled.

The session can be imported with a guided cURL text or a HAR/JSON file picker.
Selecting a file alone sends nothing; only **Import** transfers the session. An
OnlyFans window cannot be read from a NAS web page (same-origin/HttpOnly). The
downloader never asks for your password or two-factor code. Options for a future
browser helper are described in
[`docs/DSM_INTEGRATION.md`](docs/DSM_INTEGRATION.md).

## License

The application core and this package are licensed under the **GNU General
Public License v3** (see `LICENSE`). Bundled Python wheels keep their respective
licenses; see `THIRD_PARTY_NOTICES.md`.

## Links

- Source / releases:
  <https://github.com/Noa3/Synology-DSM-OnlyfansDownloader>
- Original desktop application:
  <https://github.com/Noa3/onlyfans-dl-2>
- SynoCommunity:
  <https://synocommunity.com/>
