@echo off
REM AHIA - crea il virtualenv se manca, installa le dipendenze e avvia l'app.
setlocal
cd /d "%~dp0"

REM Su Windows l'eseguibile puo' chiamarsi python o py
where python >nul 2>&1 && (set PY=python) || (set PY=py)

if not exist ".venv" (
    echo Creazione dell'ambiente virtuale...
    %PY% -m venv .venv || goto :errore_python
)

call .venv\Scripts\activate.bat

echo Installazione delle dipendenze...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt || goto :errore_pip

REM Ollama risponde?
python -c "import urllib.request,os,sys; urllib.request.urlopen(os.environ.get('OLLAMA_HOST','http://localhost:11434')+'/api/tags', timeout=5)" 2>nul
if errorlevel 1 (
    echo.
    echo ATTENZIONE: Ollama non risponde.
    echo Avvialo dal menu Start, oppure con "ollama serve" in un altro terminale.
    echo.
)

streamlit run app.py
goto :fine

:errore_python
echo.
echo Python non trovato. Installalo da https://www.python.org/downloads/
echo ricordandoti di spuntare "Add Python to PATH" durante l'installazione.
pause
exit /b 1

:errore_pip
echo.
echo Installazione delle dipendenze fallita. Controlla la connessione di rete.
pause
exit /b 1

:fine
endlocal
