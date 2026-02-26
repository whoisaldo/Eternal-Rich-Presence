# EternalRichPresence build script — produces a single portable .exe

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "Installing / updating dependencies..." -ForegroundColor Cyan
pip install -r requirements.txt

Write-Host "Building executable..." -ForegroundColor Cyan
python -m PyInstaller `
    --onefile `
    --noconsole `
    --uac-admin `
    --icon=Apple_Music_Icon.png `
    --name="EternalRichPresence" `
    --version-file=version_info.txt `
    --add-data "Apple_Music_Icon.png;." `
    --hidden-import providers `
    --hidden-import providers.base `
    --hidden-import providers.apple_music `
    --hidden-import providers.spotify `
    --hidden-import manager `
    --hidden-import presence `
    --hidden-import utils `
    --hidden-import logger `
    --hidden-import setup_gui `
    --hidden-import pystray `
    --hidden-import PIL `
    --hidden-import PIL.Image `
    --hidden-import pypresence `
    --hidden-import winrt `
    --hidden-import winrt.windows.media.control `
    --hidden-import winrt.windows.storage.streams `
    --hidden-import winrt.windows.foundation `
    --collect-all winrt `
    --collect-all pystray `
    main.py

Write-Host "Moving executable to project root..." -ForegroundColor Cyan
Move-Item -Force dist\EternalRichPresence.exe .\EternalRichPresence.exe

Write-Host "Cleaning up build artifacts..." -ForegroundColor Cyan
Remove-Item -Recurse -Force build          -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force dist           -ErrorAction SilentlyContinue
Remove-Item -Force EternalRichPresence.spec -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force __pycache__    -ErrorAction SilentlyContinue

Write-Host "Done!  EternalRichPresence.exe is ready." -ForegroundColor Green
