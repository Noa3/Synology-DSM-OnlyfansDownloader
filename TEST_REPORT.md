# Test report — OnlyFans DL for Synology DSM 2.8.0-6

Build date: **2026-11-07**
Target platform: **Synology DS723+ (r1000), DSM 7.2, Python 3.13 from SynoCommunity**
Test environment: Windows 11, CPython 3.13.12, Chromium/Playwright

> **Clarification:** The “DSM” column was **not executed** in this build
> environment because there was no access to the DS723+ (no SSH, no reachable NAS
> host). All checks marked “DSM: PENDING” must be repeated on the target device.
> They are not declared as passed here. The local tests check code, package
> layout, UI and memory behavior but do not replace a DSM installation test.

## Result summary

| Check | Result | Where |
| --- | --- | --- |
| Full Python test suite | **363 tests, 0 failures, 3 skips** | local |
| DSM-specific tests | **69 tests, 0 failures, 2 Linux skips** | local |
| DSM tests including real process groups | **69 tests, 0 failures, no skips** | Linux CI |
| Package build | **passed** | local |
| Reproducible build (twice) | **byte-identical** | local |
| Browser UI (Playwright) | **passed**, no console errors | local |
| Control service memory | **approx. 33 MiB RSS / 18.5 MiB private** | earlier local build, not re-measured |
| Streaming worker 256 MiB | **peak approx. 37.3 MiB RSS / 28.2 MiB private** | earlier local build, not re-measured |
| Installation on DS723+ | **PENDING** | DSM |
| Start/stop on DSM | **PENDING** | DSM |
| NAS reboot | **PENDING** | DSM |
| Update/download preservation | **PENDING** | DSM |
| Idle PSS on DS723+ | **PENDING** | DSM |
| Real OnlyFans session / API | **PENDING** | target account |

Windows skips the symlink permission test and two real Linux process tests. The
latter check an orphaned worker child group and stopping the service when the PID
file is missing. They run in Linux CI and are not reported as native DSM tests.

## Command run

```bash
python -m unittest discover -s tests
```

Excerpt:

```
Ran 363 tests in 118.857s
OK (skipped=3)
```

The DSM tests include:

| File | Contents |
| --- | --- |
| `tests/test_dsm_security.py` | password hashing, SessionStore 0600, redaction, login limiter |
| `tests/test_dsm_db.py` | schema, jobs, event/job limits, creator pages, manifest statistics |
| `tests/test_dsm_jobs.py` | option validation, path boundaries, profiles, proxy, schedule |
| `tests/test_dsm_worker.py` | pause/cancel, EventWriter, preview, subscriptions, download mapping |
| `tests/test_dsm_service.py` | setup/login/CSRF, permissions, folders, jobs, preview, static files, rate limit, light import |
| `tests/test_dsm_package.py` | INFO, checksum, contents, modes, JSON, shell syntax, reproducibility |
| `tests/test_dsm_resilience.py` | thread progress, write locks, NaN JSON, event tail, session changes, DSM locale, free-resub price guard, API backoff, PID reuse and Linux process trees |

In addition, `test_dsm_service.py` checks in a fresh process that the control
service does **not** import `requests`, `curl_cffi`, `PIL`, `ofdl.api` or
`ofdl.downloads`.

## Package verification

```
File:    dist/OnlyFansDL-r1000-dsm72_2.8.0-6.spk
Size:    22.01 MiB
SHA256:  6271f8f08c13ce8be689b5d5d8843a68c6558631d8c0689f7e976064183729bd
MD5(package.tgz): 1675024208a9ce6950993d2db419d0b3
```

Verified:

- `INFO`: `package=OnlyFansDL`, `version=2.8.0-6`, `arch=r1000`,
  `os_min_ver=7.2-64570`, `adminport=8765`, `adminurl=/`,
  `install_dep_packages=python313>=3.13.11-9`, MD5 checksum matches.
- `package.tgz`: `ofdl/dsm/service.py`, `ofdl/dsm/worker.py`,
  `web/index.html`, `web/static/app.js`, `ui/config`,
  `requirements-dsm.lock`, 11 wheels; **no** `__pycache__`, `.pyc`,
  `session.json` or `control.sqlite3`.
- Scripts `postinst`, `postupgrade`, `start-stop-status` are `0755`;
  `postinst` contains `ACTION="install"`, `postupgrade` `ACTION="upgrade"`;
  no `@ACTION@` remains.
- `conf/privilege`, `conf/resource`, `WIZARD_UIFILES/*`, `ui/config` are valid
  JSON; `bash -n` parses all shell scripts.
- `conf/privilege`: `run-as: package`, `sc-onlyfansdl`,
  `groupname: synocommunity`, **no** `join-groupname`, **no** `ctrl-script`;
  matches the pattern of working SynoCommunity packages.
- `conf/resource`: empty, no `data-share` resource. No automatic share creation
  or permission grant. Installer/start export no automatically determined share
  path.
- Two builds with `SOURCE_DATE_EPOCH=1794009600` are byte-identical.

  The Windows build and Linux CI build both have the SHA256 above. The release
  asset is the locally tested Windows build. Different future zlib versions
  could produce different gzip bytes.

## Browser UI

`python tools/test_web_ui.py` with Playwright (Chromium, headless, 1440×1100)
checks with a synthetic session and local manifests, without a real account:

- setup/login and main interface in seven languages; simulated DSM system
  language and language cookie, manual override and return to Auto
- first start without a library → Settings, no implicit destination
- saved path for downloads and library; manifest change immediately visible
- folder creation: rejecting confirmation creates nothing, accepting creates only
  the explicitly chosen subfolder
- file selection sends no session; import only after an explicit click
- language switching through all tabs, path stays correct; reload keeps the path
- sign-out/sign-in without a corrupted following HTTP request
- reload during a running job: status and the last 100 events appear
- only the event request fails: service stays online, job stays visible
- failed initial request: automatic retry without a manual reload
- unknown scan total without a percentage; separate file-byte display; plausible
  overall progress after scanning ends and visible 401 errors
- mobile width 375 px without overflow in Overview, Free & Trials and Settings
- no `console.error`/`pageerror` messages
- no external resources (CSP compliant)

Current dashboard screenshots are synthetic local tests, not NAS/real download
measurements: `docs/dsm-ui-dashboard.png`, `docs/dsm-ui-dashboard-en.png`.
Older illustrative screenshots (not the current storage dialog):
`docs/dsm-ui-folders.png`, `docs/dsm-ui-session.png`,
`docs/dsm-ui-session-tested.png`, `docs/dsm-ui-settings.png`.

## Memory measurement (local, indicative only)

The measurement was performed under Windows. PSS is not available there; the DSM
target refers to PSS and must be measured with `tools/measure_dsm.py` on the
DS723+. The following values come from the earlier measurement, not from a new
memory benchmark of 2.8.0-6.

| State | Processes | RSS | Private |
| --- | --- | ---: | ---: |
| Service after start | service + venv launcher | 33.0 MiB | 18.5 MiB |
| UI resources loaded | service + launcher | 33.6 MiB | 18.9 MiB |
| After 5 preview jobs | service + launcher | 33.9 MiB | 19.0 MiB |
| Streaming worker, 256 MiB | worker + launcher | **37.3 MiB peak** | 28.2 MiB |
| Import baseline download worker | worker + launcher | 39.6 MiB | 28.0 MiB |

The streaming test uses the real `run_downloads` path (manifest, byte-range
check, 256 KiB chunks, `.part` handling) against a local HTTP source; only the
host/port check was relaxed for the test. The worker does not load the file into
memory. Details: `docs/MEASUREMENT.md`.

## DSM test matrix (to complete on the DS723+)

| # | Check | Procedure | Status |
| --- | --- | --- | --- |
| 1 | Package source + Python 3.13 | SynoCommunity source, install `python313` | PENDING |
| 2 | SPK installation | Package Center → Manual Install | PENDING |
| 3 | Wizard/password | Set password, open interface | PENDING |
| 4 | Start/stop | Package Center start/stop; `start-stop-status` | PENDING |
| 5 | NAS reboot | Reboot, check service and interface | PENDING |
| 6 | Update | install new SPK over old; downloads/manifest preserved | PENDING |
| 7 | Uninstall | share/downloads remain | PENDING |
| 8 | Session import + test | import real API request, test | PENDING |
| 9 | Download | small creator, check file + manifest | PENDING |
| 10 | Large library | ~80,000 files, scan/download, cancel | PENDING |
| 11 | PSS idle | `measure_dsm.py sample --seconds 30 --interval 2` | PENDING |
| 12 | PSS with UI | browser open, 2 min, then measure | PENDING |
| 13 | PSS active | large job, `--interval 0.5` | PENDING |
| 14 | PSS after cancel | wait 30 s, worker exited? | PENDING |
| 15 | Multiple runs | sequence 3×, return to baseline | PENDING |
| 16 | Upgrade storage consent | no old path active until saved in Settings | PENDING |
| 17 | No new shares | install/start create neither OnlyFans nor OnlyFansDL | PENDING |
| 18 | User permissions | only explicitly chosen share allowed for sc-onlyfansdl | PENDING |
| 19 | Complete stop | stop service + worker + ffmpeg for active/paused/hung job | PENDING |
| 20 | Real session issues | browser/NAS in parallel, 401/429/network errors and controlled recovery | PENDING |
| 21 | Free resub | only authorized free profiles, real API compatibility | PENDING |

### Commands for DSM measurement

Copy `tools/measure_dsm.py` to the NAS (e.g. into the share) and run it with the
SynoCommunity Python:

```bash
PY=/var/packages/python313/target/bin/python3
$PY /volume1/OnlyFans/tools/measure_dsm.py snapshot --json
$PY /volume1/OnlyFans/tools/measure_dsm.py sample --seconds 30 --interval 2
```

Under **Overview → Service → Memory** the interface additionally shows PSS/RSS of
the service and the active worker.

## Known, unverified points

Linux CI on implementation commit `ffd3124d04f79b5dffd7db5f2b90721f9cf45fc5`:
[`42357026929`](https://github.com/Noa3/Synology-DSM-OnlyfansDownloader/actions/runs/42357026929),
`Ran 69 tests in 22.421s`, `OK`, no skips. Includes the real Linux tests for
worker child groups and service stop without a PID file. **Not a DSM hardware
test.**

- **No real OnlyFans session** and no real media download in this environment.
  API/signature/Cloudflare compatibility can change.
- **No DSM hardware**: installation, start/stop, reboot, update, permissions,
  SynoCommunity dependency and PSS were not run on a DS723+.
- **No 80,000-file library** on NAS hardware. The engine tests and
  manifest/legacy tests cover the logic; real scan duration depends on storage
  and HDD/SSD.
- **PSS** is available only on Linux; the local Windows values are not DSM PSS
  values.
- The worker peak for a real large download can exceed the 256 MiB test (TLS,
  curl_cffi, network buffers). Measure on DSM.
- No DSM desktop window implemented. The browser interface remains active;
  click protection/CSP are not relaxed. See `docs/DSM_INTEGRATION.md`.
- Existing unwanted NAS shares were not deleted here: no NAS access. The update
  deletes no user data. Remove the explicitly named shares in DSM only after
  checking their contents.

## Reproduction

```bash
python tools/fetch_wheels.py
python tools/build_spk.py
python -m unittest discover -s tests
```

Expectation: no test failures and a byte-identical SPK with the same
`SOURCE_DATE_EPOCH`. Browser test separately: `python tools/test_web_ui.py`
(optional developer dependency Playwright with installed Chromium).
