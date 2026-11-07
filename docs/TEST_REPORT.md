# Testbericht / Test report

Der vollständige aktuelle Bericht liegt zentral in
[`../TEST_REPORT.md`](../TEST_REPORT.md), damit keine widersprüchlichen Kopien
entstehen. / The full current report is maintained in one place:
[`TEST_REPORT.md`](https://github.com/Noa3/Synology-DSM-OnlyfansDownloader/blob/main/TEST_REPORT.md).

## 2.8.0-6

- 363 local Python tests: zero failures, three Windows skips. 69 DSM-specific
  tests: zero failures, two real-Linux skips. Linux CI ran all 69 DSM tests with
  zero failures and no skips, including real process-tree/service-stop tests.
- Browser regression: seven languages, simulated DSM locale/override, reload
  during work, separate event/boot failures, reconnection, scan/file progress,
  mobile width, explicit storage and session persistence passed locally.
- No direct NAS access: real DSM upgrade/permissions/installation, PSS and
  authenticated OnlyFans downloads remain unverified.
- No NAS folders deleted. No automatic shared-folder creation in this release.
