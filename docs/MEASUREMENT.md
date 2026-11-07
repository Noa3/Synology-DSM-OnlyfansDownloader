# Measuring memory (DS723+)

## Goal and context

Provisional development target: **at most about 50 MiB PSS for all own processes
combined at idle**. This is a target, not a guaranteed promise. Actual values
must be measured on the DS723+.

PSS (Proportional Set Size) is the fair sum across processes: shared pages are
counted proportionally. RSS counts shared pages fully in every process and is
therefore too high as a sum. The report states both values; the target refers to
**PSS**.

## Tool

`tools/measure_dsm.py` reads `/proc/<pid>/smaps_rollup` and `/proc/<pid>/status`.
It needs only the Python standard library and can run with the SynoCommunity
interpreter or a DSM system Python:

```bash
# Single snapshot
/var/packages/python313/target/bin/python3 \
  /volume1/OnlyFans/tools/measure_dsm.py snapshot --json

# Sample for 30 seconds, every 2 seconds
/var/packages/python313/target/bin/python3 \
  /volume1/OnlyFans/tools/measure_dsm.py sample --seconds 30 --interval 2

# Active work: short sampling
/var/packages/python313/target/bin/python3 \
  /volume1/OnlyFans/tools/measure_dsm.py sample --seconds 20 --interval 0.5 --json
```

The script finds processes by command line:

- `ofdl.dsm.service` → control service
- `ofdl.dsm.worker` → short-lived worker

It counts only these processes, no browser, no DSM and no other packages. Copy
`tools/measure_dsm.py` to the NAS for this (e.g. via File Station into the share)
or run it from the unpacked source. This is not needed for normal operation.

Alternatively the interface shows PSS/RSS of the control service and the active
worker under **Overview → Service → Memory** (if `/proc` is available).

## Document measurement conditions

For each measurement record:

- date/time, DSM version, model (DS723+), RAM configuration
- number of running packages and whether the browser is open
- library size (files, GiB) and storage type (HDD/SSD/NVMe)
- whether a job was running, which type and how many files/media
- network (LAN, proxy, VPN) and session state
- duration of the idle period before measurement (at least 5 minutes)

## Recommended sequence

1. **After start**: start the package, wait 5 minutes, do not open the interface.
   Run `sample --seconds 30 --interval 2`.
2. **With the interface open**: browser on Overview, wait 2 minutes, then measure
   for 30 seconds. Additionally run `tools/dsm_http_check.py --open-ui` to load
   all UI resources once.
3. **Large job**: “All active subscriptions”, all categories and types, existing
   library. During the run measure for 20–60 seconds with `--interval 0.5`.
   Record peak values.
4. **Cancellation**: cancel the job, wait 30 seconds (the worker must have
   exited), measure idle again.
5. **Multiple runs**: repeat sequence 2–4 three times. Check whether PSS/RSS
   returns to the starting value after each run.
6. **Update/restart**: restart the NAS, measure again after start. Ensure no
   orphaned worker processes remain (`ps`/`measure_dsm.py` shows only one service,
   no worker at idle).

## Results table (to fill in on the NAS)

| State | Processes | Total PSS (MiB) | Total RSS (MiB) | Worker peak (MiB) | Conditions |
| --- | ---: | ---: | ---: | ---: | --- |
| After start, 5 min idle |  |  |  | – |  |
| Interface open, 2 min |  |  |  | – |  |
| Large job running |  |  |  |  |  |
| After cancellation, 30 s |  |  |  | – |  |
| After 3 runs |  |  |  | – |  |
| After NAS restart |  |  |  | – |  |

## Local reference measurement (not DSM)

These values were measured in the build environment under Windows. They are
**not DSM proof**; PSS is not available under Windows. The venv launcher is an
additional small process that does not exist under Linux.

| State | Processes | RSS | Private |
| --- | --- | ---: | ---: |
| Control service after start | service + launcher | 33.0 MiB | 18.5 MiB |
| Control service, UI resources loaded | service + launcher | 33.6 MiB | 18.9 MiB |
| After 5 preview jobs | service + launcher | 33.9 MiB | 19.0 MiB |
| Streaming worker, 256 MiB test download | worker + launcher | **37.3 MiB peak** | 28.2 MiB |
| Import baseline download worker | worker + launcher | 39.6 MiB | 28.0 MiB |
| Import baseline preview worker | worker + launcher | 26.0 MiB | 14.3 MiB |

The 256 MiB test uses the real `run_downloads` path with manifest,
byte-range/length checks, 256 KiB chunks and a local HTTP source; only the
host/port check was relaxed for the local measurement. The peak shows that the
streaming engine does not load the file into memory.

## What the numbers do not say

- A single peak says nothing about long-term stability with 80,000 files.
- LegacyIndex may need additional memory on the first run for a creator when
  exact paths are missing. That is a worker peak, not a permanent state; the
  worker exits after the job.
- Actual network speed, TLS impersonation and Cloudflare responses can change
  runtime, not base memory usage.
- Without a real session no real media download can be measured. The test report
  explicitly marks this gap.
