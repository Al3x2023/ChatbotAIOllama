#!/usr/bin/env bash

# Script de configuración local para ChatbotAIOllama
# Este script prepara el entorno, instala dependencias y configura la base de datos.

set -e

echo "🚀 Iniciando configuración de ChatbotAIOllama..."

# 1. Verificar Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: python3 no está instalado. Por favor instálalo antes de continuar."
    exit 1
fi

# 2. Crear entorno virtual si no existe
if [ ! -d "venv" ]; then
    echo " Creando entorno virtual..."
    python3 -m venv venv
else
    echo "✅ Entorno virtual ya existe."
fi

# 3. Activar entorno virtual e instalar dependencias
echo "📥 Instalando dependencias (esto puede tardar un poco)..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 4. Configurar archivo .env
if [ ! -f ".env" ]; then
    echo "⚙️  Creando archivo .env desde .env.template..."
    cp .env.template .env
    echo "⚠️  Se ha creado un archivo .env predeterminado. Ajusta los valores si es necesario."
else
    echo "✅ El archivo .env ya existe."
fi

# 5. Ejecutar migraciones
echo "🗄️  Ejecutando migraciones de base de datos..."
python manage.py migrate

# 6. Ejecutar pipeline (opcional pero recomendado para cargar datos iniciales)
read -p "❓ ¿Deseas ejecutar el pipeline para cargar datos de UAEMEX ahora? (s/n): " run_pipeline
if [[ $run_pipeline =~ ^[Ss]$ ]]; then
    echo "🔄 Ejecutando pipeline con URLs de 'clasificadas'... (Asegúrate de tener Ollama corriendo si es necesario)"
    # Ejecuta el pipeline procesando archivos de la carpeta clasificadas
    python manage.py ejecutar_pipeline --archivo-html "clasificadas/html.txt" --archivo-pdf "clasificadas/pdfs.txt" --lote-html 1000 --lote-pdf 1000
fi

echo ""
echo "-------------------------------------------------------"
echo "✅ ¡Configuración completada con éxito!"
echo ""
echo "Para iniciar el servidor, ejecuta:"
echo "   source venv/bin/activate"
echo "   python manage.py runserver"
echo "-------------------------------------------------------"
