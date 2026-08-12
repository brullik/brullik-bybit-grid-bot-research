# M1 qualified reference campaign runbook

## Purpose and boundary

This runbook completes the remaining qualified-host measurements needed for an owner/PM Gate 1
review. It does not accept Gate 1 and does not authorize or start the Phase 2 history downloader.

Owner-approved ADR-0019 requirements for the successor admission contract:

- receipt-verified 99,999,900-row/700-instrument layout and feature trials on the same host;
- feature peak RSS no greater than 70% of observed RAM;
- local SSD/NVMe with current free bytes covering verified active-plus-building history,
  measured retained campaign scratch, and an 8 GiB operating reserve;
- stable host/storage identity and a pinned clean environment;
- an idle host during every timed measurement and every existing performance/correctness gate.

There is no longer a fixed 16-core/64-GiB/2-TiB admission rule. On checked-in evidence the owner
laptop is a hardware candidate: the present calculation requires 100,228,313,013 bytes
(93.345 GiB) free and the receipt-bound snapshot observed 193,679,237,120 bytes (180.378 GiB).

The append-only host qualification, layout/feature v3, Gate 1 review-pack v2, and campaign-plan v2
contracts now implement those requirements without changing legacy receipts. The plan must still
pass the pinned environment and fresh qualification checks before creating a campaign directory.

## 0. Verify the measured host candidate

Run without Bybit credentials on the measured volume:

```powershell
python -m benchmarks.measured_host_qualification `
  --output C:\grid-reference\host-qualification-20260812T161730Z.json
```

Use a new filename for every fresh observation; do not overwrite an earlier receipt. The current
public artifact reports `qualified-measured-reference-host`, 100,228,313,013 required
bytes, 192,452,521,984 current free bytes, and 92,224,208,971 bytes of headroom. This qualifies
hardware/storage only. It neither passes the environment doctor nor opens Gate 1/Phase 2.

Qualification accepts capacity evidence no older than 24 hours. After the checked-in observation
expires, first regenerate the lifecycle/workstation/current-universe evidence chain and pass its
new `--capacity` and `--workstation` paths. Reusing the old free-space calculation fails closed.

## 1. Build one exact clean environment

Clone the canonical public repository, synchronize `main`, and do not use a development branch or
an existing Python environment. The campaign requires Python 3.12 and the reviewed exact direct
pins in `requirements/reference-campaign.txt`.

Windows PowerShell:

```powershell
git clone https://github.com/brullik/brullik-bybit-grid-bot-research.git
Set-Location brullik-bybit-grid-bot-research
git fetch --prune origin
git switch main
git pull --ff-only origin main

py -3.12 -m venv .venv
$python = (Resolve-Path .\.venv\Scripts\python.exe).Path
& $python -m pip install -c requirements/reference-campaign.txt -e ".[data,dev]"
& $python -m pip install --no-deps -e packages/contracts -e packages/bybit-public `
  -e packages/bybit-private
& $python -m pip install --no-deps -e apps/data -e apps/research -e apps/release -e apps/live
```

Linux shell:

```bash
git clone https://github.com/brullik/brullik-bybit-grid-bot-research.git
cd brullik-bybit-grid-bot-research
git fetch --prune origin
git switch main
git pull --ff-only origin main

python3.12 -m venv .venv
PYTHON="$(pwd)/.venv/bin/python"
"$PYTHON" -m pip install -c requirements/reference-campaign.txt -e ".[data,dev]"
"$PYTHON" -m pip install --no-deps -e packages/contracts -e packages/bybit-public \
  -e packages/bybit-private
"$PYTHON" -m pip install --no-deps -e apps/data -e apps/research -e apps/release \
  -e apps/live
```

Run the complete validation through that same absolute interpreter:

```powershell
& $python -m ruff check .
& $python -m ruff format --check .
& $python -m mypy packages apps benchmarks scripts
& $python -m pytest
& $python scripts/update_manifest.py
& $python -m benchmarks.reference_environment
```

On Linux replace `& $python` with `"$PYTHON"`. The final command must return
`status=ready-for-reference-campaign`. It checks the exact interpreter/dependencies, all editable
monorepo packages, required imports, `pip check`, source manifest, canonical origin, clean `main`
at `origin/main`, and only the **names** of any present Bybit credential variables. It never reads
or prints credential values.

Do not continue if any command fails. Do not upgrade dependencies, fetch a newer commit, recreate
the environment, or set Bybit credentials after the immutable campaign plan is published.

## 2. Select the qualified evidence chain

Use the checked-in qualification and adjacent completion receipt without copying or editing
either file. Campaign-plan creation verifies both files, their transitive sources, the current
identity, volume placement, and required free bytes before it mutates the campaign root.

If the qualification is stale when a new plan is created, publish a new qualification from fresh
capacity/workstation evidence under a new filename. Do not extend the initial age threshold or
replace the old receipt.

## 3. Publish the immutable campaign plan

Use a new campaign root on the same volume. Do not reuse a failed or completed root:

```powershell
& $python -m benchmarks.reference_campaign plan `
  --campaign-root C:\grid-reference\campaign-001 `
  --reference-host-qualification `
    benchmarks/results/m1-owner-measured-host-qualification-20260812.json
```

Linux equivalent:

```bash
"$PYTHON" -m benchmarks.reference_campaign plan \
  --campaign-root /mnt/grid-reference/campaign-001 \
  --reference-host-qualification \
    benchmarks/results/m1-owner-measured-host-qualification-20260812.json
```

The command publishes `grid.reference-campaign-plan/v2` only after validating all inputs. It
rejects insufficient current free space, a different volume/host, an initially stale
qualification, a stale source manifest, a changed environment, modified qualification evidence,
or reserved output paths. The embedded qualification remains usable across the planned reboots;
status rechecks its content and current host/free space but does not reapply the initial 24-hour
age gate mid-campaign.

## 4. Follow status one action at a time

```powershell
& $python -m benchmarks.reference_campaign status `
  --plan C:\grid-reference\campaign-001\campaign-plan.json
```

Linux equivalent:

```bash
"$PYTHON" -m benchmarks.reference_campaign status \
  --plan /mnt/grid-reference/campaign-001/campaign-plan.json
```

Interpret `next_action`:

- `action=run`: execute the exact `step.argv` array (or its informational `display_command`), then
  call `status` again;
- `action=reboot`: reboot the host, start no indexing/scanning tools, return to the same checkout,
  and call `status` again; it will then expose the measurement command;
- `campaign_status=blocked-*`: stop and preserve the root for diagnosis; do not use `--force` or
  edit receipts;
- `campaign_status=complete-ready-for-owner-review`: preserve and submit the review pack for the
  explicit owner/PM decision;
- `campaign_status=complete-blocked-by-reference-results`: preserve the negative evidence and do
  not accept Gate 1.

The expected sequence is:

1. layout preparation;
2. reboot, DuckDB single-symbol measurement;
3. reboot, DuckDB universe-month measurement;
4. reboot, Polars single-symbol measurement;
5. reboot, Polars universe-month measurement;
6. layout finalization;
7. 100-million-row reference feature run;
8. Gate 1 review-pack build.

## 5. Preserve evidence

Keep the entire campaign root, including preparation, retained Parquet layouts, each JSON receipt,
final layout evidence, feature evidence, and review pack. Do not commit generated datasets or the
external campaign root to the public repository. Only a separately reviewed small public evidence
artifact may later be added to Git.

The review pack always leaves `gate_1.status=pending-owner-decision`. The owner/PM must record the
decision separately before Phase 2 work is authorized.
