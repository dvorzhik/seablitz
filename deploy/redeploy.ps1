# SeaBlitz deploy from Git: commit -> push -> server pull -> restart.
# Usage:  powershell -File deploy/redeploy.ps1 "commit message"
# NOTE: keep this file ASCII-only (Windows PowerShell reads .ps1 without BOM as ANSI).
param([string]$Message = "")

Set-Location (Join-Path $PSScriptRoot "..")

git add -A 2>&1 | Out-Null

$staged = git diff --cached --name-only 2>&1
if ($staged) {
    if ([string]::IsNullOrWhiteSpace($Message)) {
        $Message = "Update " + (Get-Date -Format "yyyy-MM-dd HH:mm")
    }
    git commit -m $Message 2>&1 | ForEach-Object { "$_" }
    if ($LASTEXITCODE -ne 0) { throw "git commit failed" }
} else {
    Write-Output "No changes to commit - deploy only."
}

git push 2>&1 | ForEach-Object { "$_" }
if ($LASTEXITCODE -ne 0) { throw "git push failed" }

ssh -o BatchMode=yes oracle1 "cd /home/ubuntu/seablitz && git pull --ff-only && .venv/bin/pip install -q -r requirements.txt && sudo systemctl restart seablitz-web seablitz-bot && sleep 3 && systemctl is-active seablitz-web seablitz-bot" 2>&1 | ForEach-Object { "$_" }

Write-Output "Deployed: https://seablitz.duckdns.org"



