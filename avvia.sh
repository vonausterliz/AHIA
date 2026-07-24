#!/usr/bin/env bash
# AHIA — crea il virtualenv se manca, installa le dipendenze e avvia l'app.
set -euo pipefail
cd "$(dirname "$0")"

[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

if ! curl -sf "${OLLAMA_HOST:-http://localhost:11434}/api/tags" > /dev/null; then
  echo "Attenzione: Ollama non risponde su ${OLLAMA_HOST:-http://localhost:11434}."
  echo "Avvialo con 'ollama serve' in un altro terminale."
fi

exec streamlit run app.py
