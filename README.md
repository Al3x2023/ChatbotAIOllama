# ChatbotAIOllama

Chatbot web en Django con integración de Ollama, scraping institucional, procesamiento de PDFs y pipeline automatizado para operación continua en VPS.

## Estructura del proyecto

La estructura completa está en `estructura_proyecto.txt`.

```text
ChatbotAIOllama/
├── chat/
├── chatbot_project/
├── scripts/
│   ├── auto_deploy_vps.sh
│   └── instalar_systemd_vps.sh
├── estructura_proyecto.txt
├── manage.py
└── requirements.txt
```

## Modo producción

El sistema ya está preparado para operar por entorno (`DJANGO_ENV`) y configuración por variables (`.env`).

Variables clave recomendadas:

```bash
DJANGO_ENV=production
DJANGO_DEBUG=false
DJANGO_SECRET_KEY=pon_aqui_una_clave_segura
DJANGO_ALLOWED_HOSTS=tu-dominio.com,IP_DEL_VPS
VPS_PUBLIC_IP=IP_DEL_VPS
DJANGO_CSRF_TRUSTED_ORIGINS=https://tu-dominio.com
DJANGO_TIME_ZONE=America/Mexico_City
DB_ENGINE=mysql
DB_NAME=uaemex_chatbot
DB_USER=usuario_db
DB_PASSWORD=password_db
DB_HOST=127.0.0.1
DB_PORT=3306
OLLAMA_URL=http://127.0.0.1:11434
MODEL_NAME=llama3.2:latest
BASE_MODEL=llama3.2:latest
UAEMEX_BASE_URL=https://www.uaemex.mx/
UAEMEX_PDF_URLS=https://url1.pdf,https://url2.pdf
UAEMEX_SEED_URLS=https://www.uaemex.mx/,https://nuevoingreso.uaemex.mx/,https://www.uaemex.mx/convocatorias.html
```

## Auto deploy pro

Script principal:

```bash
chmod +x scripts/auto_deploy_vps.sh
./scripts/auto_deploy_vps.sh
```

Qué automatiza `scripts/auto_deploy_vps.sh`:

1. `git fetch/checkout/pull` en la rama objetivo.
2. Creación y activación de virtualenv.
3. Instalación/actualización de dependencias.
4. Backup automático de `db.sqlite3` cuando aplica.
5. `python manage.py check --deploy`.
6. `migrate` y `collectstatic`.
7. Reinicio del servicio web.
8. Pipeline completo de actualización de conocimiento y modelo.
9. Healthcheck final (`/api/health/`).

Variables relevantes del deploy:

- `APP_DIR`, `BRANCH`, `PYTHON_BIN`, `VENV_DIR`
- `SERVICE_NAME`, `OLLAMA_SERVICE_NAME`
- `AUTO_INSTALL_SYSTEMD`, `APP_USER`, `APP_GROUP`, `PORT`, `WORKERS`
- `ALLOWED_HOSTS`, `SYSTEMD_ENV_FILE`
- `RUN_MIGRATIONS`, `RUN_COLLECTSTATIC`, `INSTALL_DEPS`
- `RUN_DEPLOY_CHECK`, `RUN_PIPELINE`, `PIPELINE_MAX_PAGES`
- `PIPELINE_HTML_BATCH`, `PIPELINE_PDF_BATCH`
- `PIPELINE_HTML_FILE`, `PIPELINE_PDF_FILE`
- `PIPELINE_SKIP_PDFS`, `PIPELINE_EXTRA_ARGS`
- `BACKUP_BEFORE_DEPLOY`, `BACKUP_DIR`
- `RUN_HEALTHCHECK`, `HEALTHCHECK_URL`

Healthcheck por defecto:

- `HEALTHCHECK_URL=http://127.0.0.1:8000/api/health/`

## Automatización 24/7 con systemd

Instalación automática de servicio web + timer del pipeline:

```bash
chmod +x scripts/instalar_systemd_vps.sh
APP_DIR=/root/ChatbotAIOllama \
APP_USER=root \
APP_GROUP=root \
PYTHON_BIN=/root/ChatbotAIOllama/venv/bin/python \
GUNICORN_BIN=/root/ChatbotAIOllama/venv/bin/gunicorn \
SERVICE_NAME=chatbot \
PORT=8000 \
PIPELINE_SCHEDULE="*:0/30" \
PIPELINE_HTML_BATCH=100 \
PIPELINE_PDF_BATCH=50 \
PIPELINE_HTML_FILE="clasificadas/html.txt" \
PIPELINE_PDF_FILE="clasificadas/pdfs_interesantes.txt" \
PIPELINE_SKIP_PDFS=true \
ALLOWED_HOSTS="187.77.29.135,localhost,127.0.0.1" \
./scripts/instalar_systemd_vps.sh
```

Esto crea:

- `${SERVICE_NAME}.service` para Gunicorn
- `${SERVICE_NAME}_pipeline.service` para ejecutar `manage.py ejecutar_pipeline`
- `${SERVICE_NAME}_pipeline.timer` para ejecución periódica

## Endpoints operativos

- Estado de modelo: `GET /api/estado/`
- Healthcheck de infraestructura: `GET /api/health/`

## Comando de pipeline

Pipeline completo manual:

```bash
python manage.py ejecutar_pipeline --max-pages 120
```

Uso con tu carpeta `clasificadas/`:

```bash
python manage.py ejecutar_pipeline \
  --lote-html 300 \
  --lote-pdf 150 \
  --archivo-html clasificadas/html_interesantes.txt \
  --archivo-pdf clasificadas/pdfs_interesantes.txt
```

El pipeline detecta automáticamente archivos alternos si existen:

- `clasificadas/html_interesantes.txt`
- `clasificadas/htmls_interesantes.txt`
- `clasificadas/html.txt`
- `clasificadas/pdfs_interesantes.txt`
- `clasificadas/pdfs.txt`

Opciones:

- `--lote-html`
- `--lote-pdf`
- `--archivo-html`
- `--archivo-pdf`
- `--consumir-archivos-clasificadas`
- `--no-clasificadas`
- `--skip-scraping`
- `--skip-pdfs`
- `--skip-model-update`
- `--force-model-update`

Comportamiento para cronjob:

- Si no hay cambios reales en contenido, el pipeline no actualiza modelo.
- Para detectar cambios, compara conteos y última `fecha_actualizacion` de conocimiento.
- En VPS pequeño, conviene correr timer con `PIPELINE_SKIP_PDFS=true` y procesar PDFs en lotes manuales.

Comandos de recuperación rápida en VPS:

```bash
systemctl daemon-reload
systemctl restart chatbot
systemctl status chatbot --no-pager
systemctl restart chatbot_pipeline.timer
systemctl status chatbot_pipeline.timer --no-pager
curl http://127.0.0.1:8000/api/health/
```
