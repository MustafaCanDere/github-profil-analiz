@echo off
REM Windows'ta exe derlemek icin: Python 3.10+ kurulu olmali.
python -m pip install --upgrade pyinstaller
python -m PyInstaller --clean --noconfirm --onefile --windowed --name GitHubProfilAnaliz main.py
echo.
echo Hazir: dist\GitHubProfilAnaliz.exe
pause
