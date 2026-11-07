# Architecture

## Goal

A native DSM package that uses as little memory as possible at idle and reuses
existing libraries. The existing Python core (`ofdl/`) remains the only download
engine; the desktop UI and CLI are not replaced.

## Process model

```
┌────────────────────────────────────────────────────────────┐
│ DSM Package Center / start-stop-status                     │
│   starts exactly one control service                       │
└───────────────────────────┬────────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────────┐
│ ofdl.dsm.service  (persistent, small)                      │
│  • static web interface (HTML/CSS/JS)                      │
│  • login, CSRF, password, session file                     │
│  • SQLite: settings, jobs, events, creators                │
│  • scheduling                                               │
│  • starts/monitors the worker                               │
│  • imports ONLY the standard library                        │
└───────────────┬───────────────────────────────┬────────────┘
                │ subprocess (1 job)            │ HTTP :8765
┌───────────────▼───────────────────┐   ┌───────▼────────────┐
│ ofdl.dsm.worker (short-lived)      │   │ Browser            │
│  • session, API, rules             │   │ (LAN, password)    │
│  • download engine / scan          │   └────────────────────┘
│  • Pillow preview                  │
│  • SQLite manifest in target folder│
│  • exits after the job             │
└────────────────────────────────────┘
```

The control service starts no download threads. It opens the worker as a child
process, writes its PID into the job row and waits for completion in a monitor
thread. At most **one** worker runs at a time (409 on a second start). Pause and
cancel are signalled through job-row columns; the worker checks them at its
existing `Control.checkpoint()` points (at least every 0.5 s). Cancellation
leaves completed files and resumable `.part` files in place.

On POSIX the worker also checks that its parent is still alive. If the control
service dies hard, the worker exits itself at the next checkpoint. On Windows
this check is disabled because `os.getppid()` is unreliable for detached
processes there.

## Why the control service stays small

`ofdl/dsm/service.py` deliberately does **not** import:

- `requests`, `curl_cffi`, `ofdl.api`, `ofdl.downloads`
- `PIL` / `ofdl.preview`
- `tkinter` / `ofdl.ui`

A test starts a fresh Python process, imports only the control service and
checks that these modules do not appear in `sys.modules`. The heavy libraries
are loaded only in the worker.

The service keeps no download lists, no file-tree indexes and no preview images
in memory. Creator lists live in SQLite and are read page by page (50 per page).
Events are limited to the last 3000 per job; jobs to the last 100. The WAL
database uses a 2 MiB cache and `temp_store=FILE`.

## SQLite schema (excerpt)

```sql
settings(key PRIMARY KEY, value, updated_at)
jobs(id, kind, status, payload, result, error, phase,
     progress_done, progress_total, stats, pid, exit_code,
     pause_requested, cancel_requested, created_at, started_at, finished_at)
events(id, job_id, ts, level, message)          -- last 3000 per job
creators(username PRIMARY KEY, display_name, subscription, scanned_at)
offers(account_id, username, kind, status, detail, scanned_at)
renewal_attempts(account_id, username, day, status)
```

`payload` contains only the options needed for the job. A proxy with credentials
is **not** stored in the job but in the settings table (file 0600); the interface
receives only a masked representation. The session lives in `session.json`
(0600), never in `settings`.

## Job flow

1. `POST /api/jobs` validates the options in the control service (without
   importing the heavy modules) and creates the job row.
2. The worker starts with `PYTHONPATH=<pkgdest>` and a reduced environment.
   stdout goes to `/dev/null`, stderr to `logs/job-<id>.log`.
3. The worker marks the job `running`, loads session/rules/engine and writes
   progress and events to SQLite in a throttled way. No large objects are held
   per file; the pipeline has a queue of 64 entries.
4. At the end the worker writes `completed`, `failed` or `cancelled` with a small
   result object. The control service prunes old events/jobs.
5. A cancelled or failed worker is marked `cancelled`/`failed` by the monitor if
   it could not do so itself.

## Session and login

- The web interface has its own password (PBKDF2-HMAC-SHA256, 600,000
  iterations, random salt). It is set during installation through the DSM
  wizard; without the wizard a first-time setup page appears.
- Login sets an `HttpOnly`, `SameSite=Strict` cookie with a 12-hour lifetime.
  State-changing requests additionally require a CSRF token. A foreign
  `Origin`/`Referer` is rejected.
- The OnlyFans session is read exclusively through the existing import
  (`ofdl.auth.parse_session`). The import is never executed and not logged. A
  session test is its own worker job.
- The interface shows “Imported” until a session test succeeds, then
  “Connected”. The status is stored in `settings.session_verified`.

## Folders and permissions

- `conf/resource` is empty. No shares are created or automatically granted.
  `bootstrap`, installation and start choose no library path.
- `settings.output_dir` is the only library path. Only explicit saving sets
  `library_confirmed=1`; even older automatically chosen paths need this
  confirmation. Jobs with a different path are rejected, schedules use the
  current path instead of old snapshots. A job blocks path changes.
- `conf/privilege` sets `run-as: package`, `sc-onlyfansdl` and group
  `synocommunity`. No `ctrl-script`, no root/administrator group.
- The folder dialog reads only directory names (at most 500 per level), no file
  contents. It allows no paths outside the shared volumes. Other shares work
  only if the service account has read rights there; otherwise the dialog
  reports a permission error.
- Folders newly created by the service get mode `0770`. DSM share ACLs and the
  administrator account remain in control; the package changes no group
  membership.

## Compatibility with existing downloads

The engine first checks the expected path and then the existing
`.ofdl.sqlite3`. Only if both are missing is the creator tree searched once for
old layouts (LegacyIndex). No files are deleted or renamed. An existing folder is
selected under Settings; the file structure remains unchanged.

## Scheduling

A single scheduler thread checks the `schedule` setting every 20 seconds
(enabled, `HH:MM`, saved download options). When the time is reached, no job is
active, a session exists and the job has not run today, it starts the same worker
job type as a manual download. A missed run is caught up on the same day if the
service is running. A second job is never started in parallel.

## Package lifecycle

- `postinst`/`postupgrade` create the venv, install the wheels offline
  (`--no-index --require-hashes`), check the imports and set the web password on
  first install. An upgrade does not overwrite the password.
- `start-stop-status` starts/stops the service and writes `service.pid`.
- `preupgrade`/`preuninst` stop the service.
- `postuninst` removes only private control data, venv and logs. The library and
  all downloads remain.
