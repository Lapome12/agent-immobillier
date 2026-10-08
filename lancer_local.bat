@echo off
rem Agents immobiliers en local : double-clique sur ce fichier pour tout lancer.
cd /d "%~dp0"
python -m pip install -q -r requirements.txt
python local.py %*
pause
