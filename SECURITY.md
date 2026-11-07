# Security

## Reporting

Please report security issues through the repository's GitHub issues:
<https://github.com/Noa3/Synology-DSM-OnlyfansDownloader/issues>

Do not post real session cookies, HAR files or account data in issues.
Synthetic headers and version information are sufficient for reproducible bugs.

## Model

- **One NAS user** (administrator) operates the package.
- The web interface is password-protected and intended for access on a trusted
  LAN. The default is HTTP on port 8765; external access requires an HTTPS
  reverse proxy in front.
- The control service runs as its own DSM service user `sc-onlyfansdl` and
  requests **no** root or administrator group rights.
- No `data-share` resource: installation and start create no user shares. The
  administrator grants `sc-onlyfansdl` read/write access only to the chosen
  share and confirms the library path in the app. Until then downloads and
  schedules are locked.
- The OnlyFans session is stored only locally (`var/data/session.json`, mode
  `0600`). It is not sent to third parties and not written to settings, job data
  or logs.
- The session file is not encrypted. File permissions protect it from other
  local users, not from NAS administrators/root or a compromised NAS.
- Free resubscribe is explicitly opt-in, account-bound and limited to profiles
  rechecked as regularly free. Trials and paid rebill are excluded. No POST
  retry on an uncertain outcome. The remote API offers no verified atomic price
  lock; the residual risk of a price change is shown up front.
- Login is **not DSM SSO**. The web password is independent of the DSM account.

## Implemented protections

| Area | Measure |
| --- | --- |
| Password | PBKDF2-HMAC-SHA256, 600,000 iterations, 16-byte salt, `hmac.compare_digest` |
| Login | HttpOnly cookie, `SameSite=Strict`, 12 h lifetime, optional `Secure` |
| Brute force | 5 failures per IP, 5-minute window, 60 s lock |
| CSRF | separate token per session, required for all state-changing requests |
| Origin | foreign `Origin`/`Referer` is rejected |
| Session | `session.json` 0600, atomic write, no logs |
| Database | `control.sqlite3` 0600, WAL, private directories 0700 |
| Paths | download/preview paths must stay in the allowed folder; symlink check |
| Filenames | `safe_component`/`safe_path` from the existing engine |
| Worker | separate environment, no access to control secrets beyond its job, parent watchdog |
| UI | static files, CSP without inline scripts, no external resources |
| API | size limits for JSON/import, paged queries, bounded events |

## Deliberate limits

- **HTTP on the LAN**: Without a reverse proxy, password and cookie are not
  protected by TLS. Forwarding port 8765 to the internet endangers the session.
  Use DSM reverse proxy/HTTPS, a firewall and preferably `OFDL_COOKIE_SECURE=1`
  (service environment variable).
- **File access**: The service user is deliberately unprivileged. DSM rights
  limit its file access; the app uses an explicitly saved library path. Old
  shares and ACLs are not deleted or revoked by the update. Remove unneeded
  share permissions in DSM.
- **Session import**: The pasted text can contain cookies. It is processed in the
  browser and sent to the local service over HTTP. Do not leave a HAR file open
  in a shared browser tab. Selecting a file alone transfers nothing; only Import
  sends the content. Export files contain credentials: do not share them and
  delete them securely afterwards. A foreign login window is not read; CSP and
  click protection remain active.
- **No DRM bypass**: DRM-protected media is counted and skipped. No protected
  content is decrypted.
- **No purchase automation**: Purchases and intentionally paid actions are not
  part of the DSM interface. Free subscriptions are a state-changing, separately
  authorized exception; their price-protection limits are described above.

## Resetting the password

If the web password is unknown:

1. Uninstall the package. The `OnlyFansDL` share and all downloads remain; the
   private control data is removed.
2. Reinstall the package and set a new password in the wizard.
3. Select the same library folder in the download area.

Alternatively an administrator with SSH can back up
`/var/packages/OnlyFansDL/var/data/control.sqlite3`, clean the `settings` table
and restart the service. That is a diagnostic path, not a regular installation
step.

## Logs

- `var/logs/service.log` (rotating, 2 MiB × 3)
- `var/logs/job-<id>.log` (worker stderr, 0600)

The logs contain no cookies, `x-bc` values or session text. API error messages
are deliberately sanitized. On unexpected errors the job log contains a Python
traceback; it may contain local paths but no session values.
