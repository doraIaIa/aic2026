$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv")) {
    py -3.11 -m venv .venv
}

. .\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"

if (-not (Test-Path "configs\local.toml")) {
    Copy-Item "configs\local.example.toml" "configs\local.toml"
    Write-Host "Created configs\local.toml. Edit data_root/work_root before running doctor."
}

python -m pytest -q
Write-Host "Bootstrap complete. Next: python -m aic2026.cli doctor --config configs/local.toml"
