# SeaBlitz: update server from Git and restart services (after you pushed).
# NOTE: keep this file ASCII-only (Windows PowerShell reads .ps1 without BOM as ANSI).
ssh -o BatchMode=yes oracle1 "cd /home/ubuntu/seablitz && git pull --ff-only && .venv/bin/pip install -q -r requirements.txt && sudo systemctl restart seablitz-web seablitz-bot && sleep 3 && systemctl is-active seablitz-web seablitz-bot" 2>&1 | ForEach-Object { "$_" }

Write-Output "Updated: https://seablitz.duckdns.org"


