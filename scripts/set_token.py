"""Обновляет BOT_TOKEN в .env из файла token.txt (файл в .gitignore).

Запуск:
    python scripts/set_token.py                 # .env и token.txt в корне проекта
    python scripts/set_token.py <base_dir> <token_file>
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
base = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT
token_file = Path(sys.argv[2]) if len(sys.argv) > 2 else base / "token.txt"

env_path = base / ".env"
token = token_file.read_text(encoding="utf-8").strip().splitlines()[0].strip()
if not token:
    raise SystemExit("token.txt пуст")

lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
out: list[str] = []
found = False
for line in lines:
    if line.startswith("BOT_TOKEN="):
        out.append("BOT_TOKEN=" + token)
        found = True
    else:
        out.append(line)
if not found:
    out.append("BOT_TOKEN=" + token)

env_path.write_text("\n".join(out) + "\n", encoding="utf-8")
print(f"BOT_TOKEN updated in {env_path}")
