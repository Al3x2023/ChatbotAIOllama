import os
import django
import time
from datetime import timedelta
from django.core.management import call_command
from django.utils import timezone  # <-- IMPORTANTE para fechas con zona horaria
from chat.models import ConocimientoUAEMEX, DocumentoPDF
from .model_updater import ModelUpdater
import logging

# Configurar logging
logging.basicConfig(
    filename='autonomo.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class Orchestrator:
    """
    Cerebro autónomo del sistema.
    Decide cuándo scrapear, procesar PDFs y actualizar el modelo.
    """
    
    def __init__(self):
        self.updater = ModelUpdater()
        self.ultima_actualizacion = None
        self.cambios_detectados = False

    def ejecutar_ciclo_completo(self):
        """
        Ejecuta un ciclo completo de automejora.
        """
        logging.info("🚀 Iniciando ciclo de automejora")
        
        # 1. Verificar si es momento de scrapear
        self._verificar_y_scrapear()
        
        # 2. Verificar si es momento de procesar PDFs
        self._verificar_y_procesar_pdfs()
        
        # 3. Verificar si hubo cambios significativos
        if self.cambios_detectados:
            logging.info("🔄 Cambios detectados, actualizando modelo...")
            self._actualizar_modelo()
        else:
            logging.info("⏳ Sin cambios significativos, no se actualiza modelo")
        
        logging.info("✅ Ciclo completado\n")

    def _verificar_y_scrapear(self):
        """
        Ejecuta scraper solo si han pasado más de 6 horas.
        """
        try:
            # Buscar el registro más reciente en ConocimientoUAEMEX
            ultimo = ConocimientoUAEMEX.objects.order_by('-fecha_actualizacion').first()
            
            if ultimo:
                # Usar timezone.now() en lugar de datetime.now()
                tiempo_desde_ultimo = timezone.now() - ultimo.fecha_actualizacion
                if tiempo_desde_ultimo < timedelta(hours=6):
                    logging.info(f"⏳ Último scrapeo hace {tiempo_desde_ultimo}, esperando...")
                    return
            
            logging.info("🌐 Ejecutando scraper...")
            call_command('scrape_uaemex', max_pages=30)
            self.cambios_detectados = True
            
        except Exception as e:
            logging.error(f"❌ Error en scraper: {e}")

    def _verificar_y_procesar_pdfs(self):
        """
        Procesa PDFs solo si hay nuevos o han pasado más de 24h.
        """
        try:
            ultimo_pdf = DocumentoPDF.objects.order_by('-fecha_descarga').first()
            
            if ultimo_pdf:
                tiempo_desde_ultimo = timezone.now() - ultimo_pdf.fecha_descarga
                if tiempo_desde_ultimo < timedelta(hours=24):
                    logging.info(f"⏳ Último PDF hace {tiempo_desde_ultimo}, esperando...")
                    return
            
            logging.info("📄 Procesando PDFs...")
            call_command('procesar_pdfs')
            self.cambios_detectados = True
            
        except Exception as e:
            logging.error(f"❌ Error en PDFs: {e}")

    def _actualizar_modelo(self):
        """
        Actualiza el modelo y registra la acción.
        """
        try:
            resultado = self.updater.actualizar_modelo()
            if resultado['success']:
                logging.info(f"✅ Modelo actualizado: {resultado['message']}")
                self.ultima_actualizacion = timezone.now()
            else:
                logging.error(f"❌ Error actualizando modelo: {resultado.get('error')}")
        except Exception as e:
            logging.error(f"❌ Excepción en actualización: {e}")

    def ejecutar_cada_6_horas(self):
        """
        Bucle infinito para ejecutar cada 6 horas (útil para pruebas, pero en producción usa cron).
        """
        while True:
            self.ejecutar_ciclo_completo()
            logging.info("😴 Durmiendo por 6 horas...")
            time.sleep(6 * 60 * 60)  # 6 horas