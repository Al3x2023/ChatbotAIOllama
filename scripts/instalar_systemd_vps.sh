#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/var/www/ChatbotAIOllama}"
APP_USER="${APP_USER:-www-data}"
APP_GROUP="${APP_GROUP:-www-data}"
PYTHON_BIN="${PYTHON_BIN:-$APP_DIR/.venv/bin/python}"
GUNICORN_BIN="${GUNICORN_BIN:-$APP_DIR/.venv/bin/gunicorn}"
SERVICE_NAME="${SERVICE_NAME:-chatbot}"
PORT="${PORT:-8000}"
WORKERS="${WORKERS:-3}"
PIPELINE_SCHEDULE="${PIPELINE_SCHEDULE:-*:0/30}"
PIPELINE_MAX_PAGES="${PIPELINE_MAX_PAGES:-30}"
PIPELINE_HTML_BATCH="${PIPELINE_HTML_BATCH:-5000}"
PIPELINE_PDF_BATCH="${PIPELINE_PDF_BATCH:-1000}"
PIPELINE_HTML_FILE="${PIPELINE_HTML_FILE:-clasificadas/html.txt}"
PIPELINE_PDF_FILE="${PIPELINE_PDF_FILE:-clasificadas/pdfs.txt}"
ALLOWED_HOSTS="${ALLOWED_HOSTS:-127.0.0.1,localhost}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env}"

sudo tee "/etc/systemd/system/${SERVICE_NAME}.service" >/dev/null <<EOF
[Unit]
Description=Servicio Django ${SERVICE_NAME}
After=network.target

[Service]
Type=simple
User=${APP_USER}
Group=${APP_GROUP}
WorkingDirectory=${APP_DIR}
Environment=PYTHONUNBUFFERED=1
Environment=DJANGO_ENV=production
Environment=DJANGO_DEBUG=false
Environment=DJANGO_ALLOWED_HOSTS=${ALLOWED_HOSTS}
EnvironmentFile=-${ENV_FILE}
ExecStart=${GUNICORN_BIN} chatbot_project.wsgi:application --bind 0.0.0.0:${PORT} --workers ${WORKERS} --timeout 120
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo tee "/etc/systemd/system/${SERVICE_NAME}_pipeline.service" >/dev/null <<EOF
[Unit]
Description=Pipeline de actualización ${SERVICE_NAME}
After=network.target

[Service]
Type=oneshot
User=${APP_USER}
Group=${APP_GROUP}
WorkingDirectory=${APP_DIR}
Environment=PYTHONUNBUFFERED=1
Environment=DJANGO_ENV=production
Environment=DJANGO_DEBUG=false
Environment=DJANGO_ALLOWED_HOSTS=${ALLOWED_HOSTS}
EnvironmentFile=-${ENV_FILE}
ExecStart=${PYTHON_BIN} manage.py ejecutar_pipeline --max-pages ${PIPELINE_MAX_PAGES} --lote-html ${PIPELINE_HTML_BATCH} --lote-pdf ${PIPELINE_PDF_BATCH} --archivo-html ${PIPELINE_HTML_FILE} --archivo-pdf ${PIPELINE_PDF_FILE}
EOF

sudo tee "/etc/systemd/system/${SERVICE_NAME}_pipeline.timer" >/dev/null <<EOF
[Unit]
Description=Timer pipeline ${SERVICE_NAME}

[Timer]
OnCalendar=${PIPELINE_SCHEDULE}
Persistent=true
Unit=${SERVICE_NAME}_pipeline.service

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now "${SERVICE_NAME}.service"
sudo systemctl enable --now "${SERVICE_NAME}_pipeline.timer"
sudo systemctl restart "${SERVICE_NAME}.service"
sudo systemctl list-timers --all | grep "${SERVICE_NAME}_pipeline" || true
