# Sessions, recovery, stopping and free resubscriptions

## Session persistence is not session renewal

Imported OnlyFans credentials live in the private `var/data/session.json`, mode
0600, unencrypted. They survive page reloads, package restarts and upgrades.
The app's own login cookie is separate: 12-hour lifetime, invalidated by a
service restart. Normal page reload does not stop a worker.

OnlyFans can expire/rotate cookies when a browser logs in, logs out or changes
session. Two devices using the same snapshot can encounter authentication,
network or rate-limit problems, but the client cannot reliably prove that
concurrent usage caused a failure. Avoid excessive simultaneous requests. Import
a fresh session if authentication is rejected; the NAS cannot silently read
new cookies from the other browser. No password/2FA interception.

## Temporary problems

- DSM authenticated API **GET** retries wait at least 180 seconds after network,
  HTTP 429 or 5xx failures, up to three retries. Retry-After longer than 180 is
  honored up to the 300-second bound; a longer request stops rather than retrying
  early. TLS certificate failures, authentication rejections and challenges are
  not solved by sleeping or bypassing protection.
- Retry state/countdown is stored in job statistics, visible after a reload.
  Pause/cancel remain available during backoff. Media downloads retain the
  existing downloader's bounded retry and partial-file behavior; the entire job
  is never blindly restarted (especially not one that can submit actions).
- No progress for 90 seconds produces a waiting warning, not a false claim of
  session conflict or automatic duplicate work. Worker heartbeat is separate
  from real progress. A finite network timeout should trigger retry/error;
  package stop has a forced process-group fallback for stuck native calls.
- HTTP 401/authentication rejection produces a visible job error and clears
  session verification; import/test again. Other responses include safe API
  diagnostics where available. Cookies are never shown in those diagnostics.
- A failed status/event request retains last known job data. It is not called
  "service unreachable" merely because a UI renderer or job-event fetch failed.
  An initial-load failure still installs a retry timer. No automatic duplicate
  job start occurs on refresh/reconnect.

## DSM Stop

1. Stop scheduling and reject new jobs.
2. Request cooperative cancellation (also exits a paused/retry-waiting worker).
3. After a bounded grace period, SIGTERM then SIGKILL the owned worker process
   group, including descendants such as ffmpeg. Worker groups have separate
   sessions, kernel start-time checks and per-job tokens.
4. The package stop script verifies service identity before signalling a PID,
   then runs a final cleanup. A missing service PID file is recovered by exact
   module + package-environment identity, not a broad process-name match.
5. Completed downloads stay. Partial files are eligible for the next manual or
   scheduled download according to existing resume rules.

The Linux tests exercise a worker's orphaned child and service shutdown without
a PID file. They are not a native DSM lifecycle test. DSM Package Center's
actual timeout/resource handling still needs hardware verification.

## Free & Trials tab

Scanning is read-only: active/expired subscriptions and optional explicitly
listed profiles. Results are paginated (50/page, at most 2,000 saved offers).
Trial codes and messages are not exposed in this DSM interface.

To resubscribe: enter allowed creator names/URLs, read the zero-price/race
warning and confirm. A daily NAS-time schedule is optional and off by default.
Only profiles freshly classified as **regular price 0**, not already subscribed,
are attempted. The existing core checks price once more immediately before
its single POST. Trial/paid/ambiguous profiles are skipped. No paid-rebill API
or trial-claim endpoint is used by the DSM automation.

The remote API does not offer a verified atomic zero-price lock: a price change
between checking and the server's response cannot be fully excluded. That is
why explicit consent is required even for this guarded workflow. No real
subscription actions were performed during development/testing.

A persistent per-account/profile/day reservation is written before a possible
POST. Uncertain outcomes are not retried that day. At most 200 explicitly chosen
profiles per job and 5,000 daily reservations overall. Automation is disabled
when importing a different account; disabling never requires fresh consent.
Trials may later renew at a paid price, so review/accept them on OnlyFans itself.

## Language and updates

Auto language prefers a supported explicit DSM locale hint/accessible language
cookie, then the readable DSM system default, then browser language. It does
not read DSM passwords or authenticated DSM APIs. A standalone window cannot
always know the individual DSM user's language. Manual selection overrides
Auto. Italian/Dutch/Portuguese currently cover core UI strings; missing help or
technical translations fall back to English/German.

There is no automatic GitHub updater or DSM package feed. Update by downloading
the SPK from GitHub Releases and using Package Center → Manual Install. Existing
session/settings/library are preserved; unexpected NAS shares are never created
or deleted by this version.
