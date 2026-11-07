# Testbericht / Test report

Der vollständige aktuelle Bericht liegt zentral in
[`../TEST_REPORT.md`](../TEST_REPORT.md), damit keine widersprüchlichen Kopien
entstehen. / The full current report is maintained in one place:
[`TEST_REPORT.md`](https://github.com/Noa3/Synology-DSM-OnlyfansDownloader/blob/main/TEST_REPORT.md).

## 2.8.0-4

- 346 Python tests: zero failures, one Windows symlink skip.
- 52 DSM-specific tests: zero failures.
- Browser regression: DE/EN/FR/ES, explicit storage selection, manifest path,
  folder confirmation, session file import and persistence passed locally.
- No direct NAS access: real DSM upgrade/permissions/installation, PSS and
  authenticated OnlyFans downloads remain unverified.
- No NAS folders deleted. No automatic shared-folder creation in this release.
