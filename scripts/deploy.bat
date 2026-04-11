@echo off
REM ──────────────────────────────────────────────────────────────
REM deploy.bat — Rebuild and restart the AI Trader platform
REM
REM Usage:
REM   scripts\deploy.bat              — rebuild all services
REM   scripts\deploy.bat frontend     — rebuild only frontend
REM   scripts\deploy.bat backend      — rebuild api + worker + scheduler
REM   scripts\deploy.bat --no-build   — restart without rebuilding
REM ──────────────────────────────────────────────────────────────

cd /d "%~dp0\.."

set TARGET=%1
if "%TARGET%"=="" set TARGET=all

echo ========================================
echo   AI Trader — Deploy
echo ========================================
echo.

REM ── Git pull (skip if --no-build) ─────────────────────────
if "%TARGET%"=="--no-build" goto :skip_git
where git >nul 2>&1
if errorlevel 1 goto :skip_git
if not exist ".git" goto :skip_git
echo ==^> Pulling latest code...
git pull
echo.
:skip_git

REM ── Build ─────────────────────────────────────────────────
if "%TARGET%"=="--no-build" (
    echo ==^> Skipping build --no-build
    echo.
    goto :migrate
)
if "%TARGET%"=="frontend" (
    echo ==^> Building frontend...
    docker compose build frontend
    echo.
    goto :migrate
)
if "%TARGET%"=="backend" (
    echo ==^> Building backend services...
    docker compose build api
    echo.
    goto :migrate
)
if "%TARGET%"=="all" (
    echo ==^> Building all services...
    docker compose build api frontend
    echo.
    goto :migrate
)
echo Unknown target: %TARGET%
echo Usage: deploy.bat [all^|frontend^|backend^|--no-build]
exit /b 1

:migrate
REM ── Database migrations ───────────────────────────────────
echo ==^> Starting database...
docker compose up -d postgres redis
echo     Waiting for database to be healthy...
timeout /t 3 /nobreak >nul

echo ==^> Running database migrations...
docker compose run --rm api alembic upgrade head
echo.

REM ── Restart services ──────────────────────────────────────
if "%TARGET%"=="frontend" (
    echo ==^> Restarting frontend...
    docker compose up -d frontend caddy
    goto :status
)
if "%TARGET%"=="backend" (
    echo ==^> Restarting backend...
    docker compose up -d api worker scheduler
    goto :status
)
echo ==^> Restarting all services...
docker compose up -d

:status
echo.
echo ==^> Services:
docker compose ps
echo.
echo ========================================
echo   Deploy complete!
echo   Open http://localhost to view the app
echo ========================================
