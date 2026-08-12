# M1 external reference campaign runbook

## Purpose and boundary

This runbook completes the remaining external-host measurements needed for an owner/PM Gate 1
review. It does not accept Gate 1 and does not authorize or start the Phase 2 history downloader.

Required host and volume:

- at least 16 observed physical/high-performance cores;
- at least 64 GiB RAM;
- an NVMe campaign volume of at least 2 TiB;
- a separate backup destination sized by the owner;
- an idle host during every timed measurement.

The current owner computer does not meet this profile. Run every command below on the qualifying
host from one clean checkout of the repository.

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

## 2. Capture the qualifying host

Choose a dedicated root on the measured NVMe volume. The example uses `D:\grid-reference`:

```powershell
& $python -m benchmarks.workstation_snapshot `
  --output D:\grid-reference\reference-host.json
```

Linux equivalent:

```bash
"$PYTHON" -m benchmarks.workstation_snapshot \
  --output /mnt/grid-reference/reference-host.json
```

Verify the artifact and receipt exist. Its status must be
`meets-documented-full-research-profile`; the campaign preflight independently checks it again.

## 3. Publish the immutable campaign plan

Use a new campaign root on the same volume. Do not reuse a failed or completed root:

```powershell
& $python -m benchmarks.reference_campaign plan `
  --campaign-root D:\grid-reference\campaign-001 `
  --reference-host-evidence D:\grid-reference\reference-host.json
```

Linux equivalent:

```bash
"$PYTHON" -m benchmarks.reference_campaign plan \
  --campaign-root /mnt/grid-reference/campaign-001 \
  --reference-host-evidence /mnt/grid-reference/reference-host.json
```

The command validates all inputs before creating `campaign-plan.json` and its receipt. It rejects
the current machine, a different volume, a stale source manifest, modified evidence, or reserved
output paths.

## 4. Follow status one action at a time

```powershell
& $python -m benchmarks.reference_campaign status `
  --plan D:\grid-reference\campaign-001\campaign-plan.json
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
