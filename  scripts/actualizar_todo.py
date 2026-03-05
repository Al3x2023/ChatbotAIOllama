#!/usr/bin/env python
"""
Script para ejecutar todo el proceso de actualización:
1. Scraping web
2. Procesamiento de PDFs
3. Actualización del modelo
"""
import os
import sys
import django
import time

# Configurar Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'chatbot_project.settings')
django.setup()

from django.core.management import call_command
from chat.services.model_updater import ModelUpdater

def main():
    print("=" * 50)
    print("🔄 INICIANDO ACTUALIZACIÓN COMPLETA DEL CHATBOT UAEMEX")
    print("=" * 50)
    
    # Paso 1: Scraping web
    print("\n📡 PASO 1: Scraping del sitio web de UAEMEX")
    print("-" * 30)
    try:
        call_command('scrape_uaemex', max_pages=30)
        print("✅ Scraping completado")
    except Exception as e:
        print(f"❌ Error en scraping: {e}")
    
    time.sleep(2)
    
    # Paso 2: Procesar PDFs
    print("\n📄 PASO 2: Procesando PDFs")
    print("-" * 30)
    try:
        call_command('procesar_pdfs')
        print("✅ PDFs procesados")
    except Exception as e:
        print(f"❌ Error procesando PDFs: {e}")
    
    time.sleep(2)
    
    # Paso 3: Actualizar modelo Ollama
    print("\n🤖 PASO 3: Actualizando modelo Ollama")
    print("-" * 30)
    try:
        updater = ModelUpdater()
        resultado = updater.actualizar_modelo()
        
        if resultado['success']:
            print(f"✅ {resultado['message']}")
        else:
            print(f"❌ {resultado['message']}")
            if 'error' in resultado:
                print(f"   Error: {resultado['error']}")
    except Exception as e:
        print(f"❌ Error actualizando modelo: {e}")
    
    print("\n" + "=" * 50)
    print("🏁 ACTUALIZACIÓN COMPLETADA")
    print("=" * 50)

if __name__ == '__main__':
    main()