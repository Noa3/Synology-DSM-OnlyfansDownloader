# DSM desktop window and session import

## Current release: 2.8.0-4

The package still opens its standalone web UI. It does not claim to be a
File Station-style DSM desktop application. App login remains separate from DSM.

## DSM desktop window: possible, not enabled yet

A DSM desktop window can host a package UI. The community documents a `legacy`
window (`appWindow`, dimensions) rather than the current `.url` launcher.
Changing that flag alone is not a secure implementation:

- HTTPS DSM cannot embed the HTTP service on port 8765 (mixed content).
- Different ports are different origins. Current `X-Frame-Options: SAMEORIGIN`
  and CSP `frame-ancestors 'self'` intentionally block that embedding.
- A robust integration needs an HTTPS, same-origin package gateway/reverse proxy,
  correct asset/API/cookie paths, authenticated access, and real DSM 7.2 tests.
- Disabling browser security, allowing arbitrary framing or using a remote
  credential-capturing proxy is not an acceptable workaround.

No such proxy or speculative DSM configuration is shipped in 2.8.0-4. The
control service and one-worker memory model are retained.

References:

- [Synology application config](https://help.synology.com/developer-guide/integrate_dsm/config.html)
- [Community window configuration](https://www.synology-forum.de/wiki/Aufbau_der_Datei_%27config%27)

## Simplest current session import

1. Open OnlyFans in your normal browser and sign in there, including 2FA.
2. Developer tools → Network → an `/api2/v2/` request → Copy as cURL (bash).
3. Paste into Session → Import → Test session.

Alternatively load your own HAR/JSON/cURL export through the file picker, review
and press Import. Selecting a file alone sends nothing to the NAS. Prefer a
single cURL request: full HAR exports may contain unrelated secrets or redact
the required authentication headers. Never execute the copied command.

Cookies are credentials. Do not share cURL/HAR/session files. Remove exports
after importing. The app never requests your OnlyFans password or 2FA code.

## Why not a login iframe with automatic capture?

The browser's same-origin policy prevents a NAS page from reading an OnlyFans
tab/iframe, its network requests or cookies. HttpOnly cookies are not available
to ordinary page scripts. The site may additionally disallow framing. A login
window alone therefore cannot provide the requested automatic session import.

Potential future option: a small, separately reviewed browser extension with
explicit OnlyFans-only permissions, user-triggered capture, a preview of fields
to transfer, and explicit confirmation of the NAS destination over HTTPS. No
silent cookie access, wildcard permissions or automatic background transfer.
This needs a separate implementation and browser-specific testing; it is not
part of this release. A remote browser on the NAS would add substantial RAM,
browser-profile secrets and maintenance, contrary to the small-runtime goal.

## Storage consent and old folders

2.8.0-4 creates no shared folders and uses no library until the user explicitly
saves an existing path. Older automatically created shares are **not deleted**.
Synology's data-share worker specifies `Release(): Does nothing` to preserve
personal data: [official documentation](https://help.synology.com/developer-guide/resource_acquisition/data_share.html).

If `/volume1/OnlyFans` and `/volume1/OnlyFansDL` are unwanted, inspect/back up
their contents, stop the old package, upgrade, and remove those specific shares
in DSM Control Panel → Shared Folder. **Deleting a share deletes its contents.**
No cleanup routine in the update deletes user data or guesses whether a share
is safe to remove. Grant only the chosen share to `sc-onlyfansdl`, then save its
library path in Settings. Old grants can be revoked manually in DSM.
