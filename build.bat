@echo off
REM ============================================================
REM Universal Library - Build Script
REM ============================================================
REM
REM This script builds a portable one-folder distribution using PyInstaller.
REM
REM Prerequisites:
REM   - Python 3.10+
REM   - PyInstaller: pip install pyinstaller
REM   - All project dependencies installed
REM   - Git (for version detection from tags)
REM
REM Output:
REM   dist/UniversalLibrary/
REM       UniversalLibrary.exe
REM       _internal/
REM       storage/    (empty folder for library data)
REM
REM ============================================================

echo.
echo ============================================
echo    Universal Library - Build Script
echo ============================================
echo.

REM Navigate to script directory
cd /d "%~dp0"

REM Check if PyInstaller is installed
where pyinstaller >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: PyInstaller is not installed.
    echo Please install it with: pip install pyinstaller
    pause
    exit /b 1
)

REM ============================================================
REM Detect Version from Git Tags
REM ============================================================
echo [1/5] Detecting version from git tags...

REM Get the latest git tag
git describe --tags --abbrev=0 > universal_library\version.txt 2>nul
set /p APP_VERSION=<universal_library\version.txt

if "%APP_VERSION%"=="" (
    echo       WARNING: No git tags found. Using default version 1.0.0
    echo 1.0.0> universal_library\version.txt
    set APP_VERSION=1.0.0
) else (
    echo       Detected version: %APP_VERSION%
)

REM Parse version for addon injection (strip 'v' prefix if present)
set CLEAN_VERSION=%APP_VERSION:v=%
for /f "tokens=1-3 delims=." %%a in ("%CLEAN_VERSION%") do (
    set MAJOR=%%a
    set MINOR=%%b
    set PATCH=%%c
)
if "%PATCH%"=="" set PATCH=0
echo       Parsed version: %MAJOR%.%MINOR%.%PATCH%

REM Inject version into addon __init__.py
echo [1.5/5] Injecting version into addon...
powershell -Command "(Get-Content 'UL_blender_plugin\__init__.py') -replace '\"version\": \(\d+, \d+, \d+\)', '\"version\": (%MAJOR%, %MINOR%, %PATCH%)' | Set-Content 'UL_blender_plugin\__init__.py'"
echo       Addon version set to (%MAJOR%, %MINOR%, %PATCH%)

REM Clean previous builds
echo [2/5] Cleaning previous builds...
if exist "build" (
    rmdir /s /q "build"
    echo       Removed: build/
)
if exist "dist" (
    rmdir /s /q "dist"
    echo       Removed: dist/
)

REM Run PyInstaller
echo.
echo [3/5] Running PyInstaller...
echo       This may take a few minutes...
echo.
pyinstaller build_spec.spec --noconfirm

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: PyInstaller build failed!
    pause
    exit /b 1
)

REM Create storage folder
echo.
echo [4/5] Creating storage folder...
if not exist "dist\UniversalLibrary\storage" (
    mkdir "dist\UniversalLibrary\storage"
    echo       Created: dist/UniversalLibrary/storage/
)

REM Create a README for the portable installation
echo.
echo [5/5] Creating portable installation info...
(
echo Universal Library - Portable Installation
echo ==========================================
echo.
echo This is a portable installation. All your data will be stored in the
echo 'storage' folder next to the executable.
echo.
echo Structure:
echo   UniversalLibrary.exe  - Main application
echo   _internal/            - Application dependencies
echo   storage/              - Your asset library data
echo.
echo First Launch:
echo   On first launch, a setup wizard will guide you through configuring
echo   your library storage location. The storage folder is already created
echo   for you.
echo.
echo Blender Plugin:
echo   Install the Blender addon from Settings ^> Blender Integration.
echo.
echo Moving Your Library:
echo   To move your library to another computer, simply copy this entire
echo   folder to the new location.
echo.
) > "dist\UniversalLibrary\README.txt"
echo       Created: dist/UniversalLibrary/README.txt

REM Restore addon version placeholder (for git cleanliness)
echo.
echo Restoring addon version placeholder...
powershell -Command "(Get-Content 'UL_blender_plugin\__init__.py') -replace '\"version\": \(\d+, \d+, \d+\)', '\"version\": (1, 0, 0)' | Set-Content 'UL_blender_plugin\__init__.py'"
echo Done.

REM Done
echo.
echo ============================================
echo    Build Complete! (Version: %APP_VERSION%)
echo ============================================
echo.
echo Output: dist\UniversalLibrary\
echo.
echo You can now:
echo   1. Run: dist\UniversalLibrary\UniversalLibrary.exe
echo   2. Copy the entire 'UniversalLibrary' folder for distribution
echo.
pause
