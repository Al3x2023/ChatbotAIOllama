#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/root/ChatbotAIOllama}"
BRANCH="${BRANCH:-main}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-$APP_DIR/venv}"
SERVICE_NAME="${SERVICE_NAME:-chatbot}"
OLLAMA_SERVICE_NAME="${OLLAMA_SERVICE_NAME:-ollama}"
AUTO_INSTALL_SYSTEMD="${AUTO_INSTALL_SYSTEMD:-true}"
APP_USER="${APP_USER:-root}"
APP_GROUP="${APP_GROUP:-root}"
GUNICORN_BIN="${GUNICORN_BIN:-$VENV_DIR/bin/gunicorn}"
PORT="${PORT:-8000}"
WORKERS="${WORKERS:-3}"
ALLOWED_HOSTS="${ALLOWED_HOSTS:-127.0.0.1,localhost,187.77.29.135}"
SYSTEMD_ENV_FILE="${SYSTEMD_ENV_FILE:-$APP_DIR/.env}"
RUN_MIGRATIONS="${RUN_MIGRATIONS:-true}"
RUN_COLLECTSTATIC="${RUN_COLLECTSTATIC:-true}"
RESTART_SERVICE="${RESTART_SERVICE:-true}"
RESTART_OLLAMA="${RESTART_OLLAMA:-false}"
INSTALL_DEPS="${INSTALL_DEPS:-true}"
RUN_DEPLOY_CHECK="${RUN_DEPLOY_CHECK:-true}"
RUN_PIPELINE="${RUN_PIPELINE:-true}"
PIPELINE_MAX_PAGES="${PIPELINE_MAX_PAGES:-120}"
PIPELINE_HTML_BATCH="${PIPELINE_HTML_BATCH:-100}"
PIPELINE_PDF_BATCH="${PIPELINE_PDF_BATCH:-50}"
PIPELINE_HTML_FILE="${PIPELINE_HTML_FILE:-clasificadas/html.txt}"
PIPELINE_PDF_FILE="${PIPELINE_PDF_FILE:-clasificadas/pdfs_interesantes.txt}"
PIPELINE_SKIP_PDFS="${PIPELINE_SKIP_PDFS:-false}"
PIPELINE_EXTRA_ARGS="${PIPELINE_EXTRA_ARGS:-}"
BACKUP_BEFORE_DEPLOY="${BACKUP_BEFORE_DEPLOY:-true}"
BACKUP_DIR="${BACKUP_DIR:-$APP_DIR/backups}"
HEALTHCHECK_URL="${HEALTHCHECK_URL:-http://127.0.0.1:8000/api/health/}"
RUN_HEALTHCHECK="${RUN_HEALTHCHECK:-true}"

cd "$APP_DIR"

if [ ! -d ".git" ]; then
  echo "No se encontró un repositorio git en $APP_DIR"
  exit 1
fi

git fetch origin "$BRANCH"
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"

if [ ! -d "$VENV_DIR" ]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

if [ "$INSTALL_DEPS" = "true" ]; then
  pip install --upgrade pip
  pip install -r requirements.txt
fi

if [ "$BACKUP_BEFORE_DEPLOY" = "true" ] && [ -f "db.sqlite3" ]; then
  mkdir -p "$BACKUP_DIR"
  cp "db.sqlite3" "$BACKUP_DIR/db_$(date +%Y%m%d_%H%M%S).sqlite3"
fi

if [ "$RUN_DEPLOY_CHECK" = "true" ]; then
  DJANGO_DEBUG=false DJANGO_ENV=production python manage.py check --deploy
fi

if [ "$RUN_MIGRATIONS" = "true" ]; then
  python manage.py migrate --noinput
fi

if [ "$RUN_COLLECTSTATIC" = "true" ]; then
  python manage.py collectstatic --noinput
fi

if [ "$RESTART_SERVICE" = "true" ]; then
  if ! systemctl list-unit-files | grep -q "^${SERVICE_NAME}\.service"; then
    if [ "$AUTO_INSTALL_SYSTEMD" = "true" ] && [ -f "$APP_DIR/scripts/instalar_systemd_vps.sh" ]; then
      APP_DIR="$APP_DIR" APP_USER="$APP_USER" APP_GROUP="$APP_GROUP" PYTHON_BIN="$VENV_DIR/bin/python" GUNICORN_BIN="$GUNICORN_BIN" SERVICE_NAME="$SERVICE_NAME" PORT="$PORT" WORKERS="$WORKERS" PIPELINE_MAX_PAGES="$PIPELINE_MAX_PAGES" PIPELINE_HTML_BATCH="$PIPELINE_HTML_BATCH" PIPELINE_PDF_BATCH="$PIPELINE_PDF_BATCH" PIPELINE_HTML_FILE="$PIPELINE_HTML_FILE" PIPELINE_PDF_FILE="$PIPELINE_PDF_FILE" PIPELINE_SKIP_PDFS="$PIPELINE_SKIP_PDFS" PIPELINE_EXTRA_ARGS="$PIPELINE_EXTRA_ARGS" ALLOWED_HOSTS="$ALLOWED_HOSTS" ENV_FILE="$SYSTEMD_ENV_FILE" bash "$APP_DIR/scripts/instalar_systemd_vps.sh"
    else
      echo "No existe ${SERVICE_NAME}.service y no se pudo auto-instalar."
      exit 1
    fi
  fi
  sudo systemctl restart "$SERVICE_NAME"
  sudo systemctl is-active --quiet "$SERVICE_NAME"
fi

if [ "$RESTART_OLLAMA" = "true" ]; then
  sudo systemctl restart "$OLLAMA_SERVICE_NAME"
  sudo systemctl is-active --quiet "$OLLAMA_SERVICE_NAME"
fi

if [ "$RUN_PIPELINE" = "true" ]; then
  PIPELINE_ARGS=()
  if [ "$PIPELINE_SKIP_PDFS" = "true" ]; then
    PIPELINE_ARGS+=("--skip-pdfs")
  fi
  if [ -n "$PIPELINE_EXTRA_ARGS" ]; then
    PIPELINE_ARGS+=($PIPELINE_EXTRA_ARGS)
  fi
  python manage.py ejecutar_pipeline \
    --max-pages "$PIPELINE_MAX_PAGES" \
    --lote-html "$PIPELINE_HTML_BATCH" \
    --lote-pdf "$PIPELINE_PDF_BATCH" \
    --archivo-html "$PIPELINE_HTML_FILE" \
    --archivo-pdf "$PIPELINE_PDF_FILE" \
    "${PIPELINE_ARGS[@]}"
fi

if [ "$RUN_HEALTHCHECK" = "true" ]; then
  if command -v curl >/dev/null 2>&1; then
    curl -fsS "$HEALTHCHECK_URL" >/dev/null
  elif command -v wget >/dev/null 2>&1; then
    wget -q -O- "$HEALTHCHECK_URL" >/dev/null
  else
    python - <<'PY'
import os
import urllib.request
urllib.request.urlopen(os.environ.get("HEALTHCHECK_URL", "http://127.0.0.1:8000/api/health/"), timeout=10).read()
PY
  fi
fi

echo "Despliegue completado para rama $BRANCH en $APP_DIR"
