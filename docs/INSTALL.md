# Installing on DSM 7.2 (DS723+)

This guide describes the complete path through the DSM interface. **No SSH,
Python or pip commands** are required for installation, setup or operation.

## 1. Add the SynoCommunity package source

1. Open DSM → **Package Center**.
2. **Settings** → **Package Sources** → **Add**.
3. Name: `SynoCommunity`
4. Location: `https://packages.synocommunity.com/`
5. Save. The source is needed for the Python 3.13 runtime because Synology does
   not provide Python 3.13 for DSM 7.2 itself.

## 2. Install the package

1. Download `OnlyFansDL-r1000-dsm72_2.8.0-6.spk` from the release.
2. Package Center → **Manual Install** → choose the file.
3. DSM shows the **Python 3.13** dependency and installs it automatically from
   the SynoCommunity source.
4. In the install dialog enter the **web password** (at least 10 characters)
   twice. It applies only to the OnlyFans DL interface, not to DSM.
5. Finish the installation.

If installation stops with “Python 3.13 not found”:

- Check that the SynoCommunity source is correct.
- Search for `Python 3.13` in Package Center and install it first.
- Then install the OnlyFans DL package again.

## 3. Open the interface

After installation, **OnlyFans DL** appears in the DSM main menu. Alternatively
click **Open** in Package Center or visit:

```
http://<NAS-IP>:8765/
```

The interface runs on port **8765**. If the port is in use, DSM reports a port
conflict during installation; in that case change the service using the port
(the port is fixed in this package).

Sign in with the password set in the wizard.

## 4. Choose the download folder

1. The package creates **no** shared folders. In DSM open **Control Panel →
   Shared Folder → the desired share → Edit → Permissions**.
2. Switch to **System internal user** and grant `sc-onlyfansdl`
   **Read/Write** for exactly this share. Do not use the administrators group.
3. In the app open **Settings → Library path → Browse**, choose an existing
   folder and **Save path**. Even after an upgrade the path must be explicitly
   confirmed once. Until then downloads and schedules do not run.
4. The same saved path applies to **Downloads**, **Library** and the schedule.
   An old destination in saved schedule settings is not reused. An existing
   folder is not renamed or emptied; `.ofdl.sqlite3`, `.part` files and the
   existing structure remain unchanged.

New subfolders can be created in the dialog with **Create** and explicit
confirmation. Only an existing folder can be saved as the library. Changing it
is blocked while a job is running.

### Removing unwanted shares from older versions

The update deletes neither `/volume1/OnlyFans` nor `/volume1/OnlyFansDL`. If they
are unwanted: inspect/back up the contents, stop the old package, update, then
delete those specific shares under **DSM → Control Panel → Shared Folder**.
**Deleting a share also deletes its contents.** Remove old, no longer needed
permissions for `sc-onlyfansdl` in DSM as well.

## 5. Import the OnlyFans session

1. In your logged-in browser on `onlyfans.com`, copy a request to
   `https://onlyfans.com/api2/v2/...`:
   - Chrome/Edge: Developer tools → Network → request → **Copy as cURL (bash)**
   - or HAR/JSON/headers from an API request.
2. In the OnlyFans DL interface → **Session**, paste the text or choose your own
   HAR/JSON/cURL file. Selecting a file alone transfers nothing to the NAS.
3. Click **Import**. The interface shows the account ID.
4. Click **Test session**. Only after a successful test does the status show
   **Connected**. The test is its own worker job and exits afterwards.
5. On errors: copy a fresh request from the normal browser, use the same network
   connection, check the NAS clock.

The session is stored at
`/var/packages/OnlyFansDL/var/data/session.json` with file mode `0600`. It does
not appear in settings, job data or logs.

Enter your password and two-factor code only on OnlyFans, not in this app.
Exports contain credentials: do not share them and delete them after import.
An embedded login cannot be adopted automatically because of browser isolation.
See [DSM integration](DSM_INTEGRATION.md).

## 6. Creators and downloads

- Enable **All active subscriptions**, or
- **Load subscriptions** and tick individual creators, or
- enter names/profile URLs manually.
- Choose categories (Posts, Archived, Stories, Messages, Purchased), media types
  (Photos, Videos, Audio) and options (albums, category subfolders, preview).
- Click **Start download**.
- **Overview** shows progress, statistics and events. **Pause** stops the job;
  **Cancel** ends it while finished files are kept.
- **Scan only** writes no media and shows the planned files in the event log.

At most one job runs at a time. A second start is rejected with a notice.

## 7. Schedule

**Settings** tab:

- Enable **Start daily download automatically**.
- Choose a time in NAS time.
- **Save schedule**.

The schedule uses the last saved download settings. A missed run is caught up on
the same day if the service is running. It does not start without a session or
while a job is running.

## 8. Library and manifest

The **Library** tab shows:

- the chosen folder,
- whether `.ofdl.sqlite3` exists,
- number and size of manifested files,
- free space.

The numbers come from the manifest, not from a full file scan. With around
80,000 files this keeps the interface fast and memory-friendly. The first run
after a migration can take longer because the engine checks old layouts once;
later runs use exact paths and the manifest.

## Free & Trials / free resubscriptions

The **Free & Trials** tab can scan active/expired subscriptions and explicitly
listed profiles read-only for offers. **Scan offers** performs no subscriptions.
For free resubscriptions, enter only the desired profiles in the allowlist,
confirm the notice and either check/subscribe now or save the daily NAS time.
The default is disabled.

Trial and paid profiles are never accepted automatically. Trials can later renew
at a paid price; review them on OnlyFans. Even for free profiles, a price change
between check and server response cannot be fully excluded. Uncertain POST
results are not repeated on the same day. Changing account disables automation.

## 9. Update

1. Download the new `.spk` from the release.
2. Package Center → Manual Install.
3. DSM recognizes the upgrade. Settings, session, venv and downloads remain;
   wheels are reinstalled if needed.
4. The web password remains unchanged.

There is currently **no automatic update from GitHub** and no dedicated DSM
package feed. A DSM toggle that may be visible does not create that connection
itself. Install release SPKs manually.

## 10. Uninstall

Package Center → OnlyFans DL → Uninstall.

This removes the private control data, the venv and the logs. The
`OnlyFansDL`/`OnlyFans` shares and all downloaded files are **not** removed. A
later reinstall finds the library again when the same folder is selected.

## Troubleshooting

| Symptom | Cause / solution |
| --- | --- |
| “Python 3.13 not found” | SynoCommunity source missing or `python313` not installed. Check the source, install Python 3.13, install the package again. |
| Package does not start | Package Center → view log; also `/var/packages/OnlyFansDL/var/logs/service.log` (readable only via SSH/File Station). Common cause: port 8765 in use. |
| Login does not work | Use the password from the install wizard. If forgotten, uninstall and reinstall (downloads remain) or reset the control data. |
| “No session configured” | Import and test a session under **Session**. |
| Session test fails | Copy the request from `onlyfans.com/api2/v2/`, not another page. The session may be tied to a network/IP; test on the same network as the browser. Cloudflare challenges are not bypassed. |
| “Package requires root” / administrator warning | Replace old versions 2.8.0-1/2.8.0-2. 2.8.0-6 uses the SynoCommunity privilege pattern without root/administrator group rights. If the warning persists, report the exact DSM version and message. |
| Download folder not writable | In DSM grant the system internal user `sc-onlyfansdl` Read/Write only for the desired share; then save the existing path in Settings. |
| No DSM menu entry | Restart the package; `reloadui` is set during installation. Alternatively open `http://<NAS-IP>:8765/` directly. |
| Many files, slow first run | Expected with old layouts; later runs use the manifest. No media is held permanently in the control service. |

## Security notice

The interface is intended for access on a trusted LAN. For access over the
internet use a DSM reverse proxy with HTTPS and do not expose port 8765
directly. The web password is its own login, not DSM single sign-on.
