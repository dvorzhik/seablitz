# Перевыкладка SeaBlitz на сервер oracle1 (запуск из корня проекта).
# Использование:  powershell -File deploy/redeploy.ps1
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

# .env НЕ включаем — он хранится на сервере и не перезаписывается.
tar -czf seablitz.tgz app bot static requirements.txt
scp -o BatchMode=yes seablitz.tgz oracle1:/home/ubuntu/seablitz/

ssh -o BatchMode=yes oracle1 "cd /home/ubuntu/seablitz && tar -xzf seablitz.tgz && .venv/bin/pip install -q -r requirements.txt && sudo systemctl restart seablitz-web seablitz-bot && sleep 3 && echo '--- status ---' && systemctl is-active seablitz-web seablitz-bot"

Remove-Item seablitz.tgz -ErrorAction SilentlyContinue
Write-Output "Deployed OK: https://seablitz.duckdns.org"
