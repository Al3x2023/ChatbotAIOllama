@echo off
setlocal enabledelayedexpansion

echo 🚀 Iniciando configuración de ChatbotAIOllama en Windows...

:: 1. Verificar Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Error: python no está instalado o no está en el PATH. Por favor instálalo desde python.org.
    pause
    exit /b 1
)

:: 2. Crear entorno virtual si no existe
if not exist "venv" (
    echo 📦 Creando entorno virtual...
    python -m venv venv
) else (
    echo ✅ Entorno virtual ya existe.
)

:: 3. Activar entorno virtual e instalar dependencias
echo 📥 Instalando dependencias (esto puede tardar un poco)...
call venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt

:: 4. Configurar archivo .env
if not exist ".env" (
    echo ⚙️  Creando archivo .env desde .env.template...
    copy .env.template .env
    echo ⚠️  Se ha creado un archivo .env predeterminado. Ajusta los valores si es necesario.
) else (
    echo ✅ El archivo .env ya existe.
)

:: 5. Ejecutar migraciones
echo 🗄️  Ejecutando migraciones de base de datos...
python manage.py migrate

:: 6. Ejecutar pipeline (opcional)
set /p run_pipeline="❓ ¿Deseas ejecutar el pipeline para cargar datos de UAEMEX ahora? (s/n): "
if /i "%run_pipeline%"=="s" (
    echo 🔄 Ejecutando pipeline con URLs de 'clasificadas'... (Asegúrate de tener Ollama corriendo si es necesario)
    :: Ejecuta el pipeline procesando archivos de la carpeta clasificadas
    python manage.py ejecutar_pipeline --archivo-html "clasificadas/html.txt" --archivo-pdf "clasificadas/pdfs.txt" --lote-html 1000 --lote-pdf 1000
)

echo.
echo -------------------------------------------------------
echo ✅ ¡Configuración completada con éxito!
echo.
echo Para iniciar el servidor, ejecuta:
echo    venv\Scripts\activate
echo    python manage.py runserver
echo -------------------------------------------------------
pause
