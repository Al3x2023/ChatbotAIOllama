from django.core.management.base import BaseCommand
from chat.services.scraper_service import ScraperUAEMEX
from chat.services.pdf_service import PDFService
from chat.services.model_updater import ModelUpdater
from chat.models import ConocimientoUAEMEX
import hashlib
import os

class Command(BaseCommand):
    help = 'Ejecuta el proceso automático de actualización: scraping, PDFs y modelo'

    def handle(self, *args, **options):
        self.stdout.write("=== INICIANDO ACTUALIZACIÓN AUTOMÁTICA ===")
        
        # 1. Scraping web
        self.stdout.write("\n[1/3] Ejecutando scraping web...")
        scraper = ScraperUAEMEX()
        # Podrías pasar un argumento para limitar páginas
        resultados_scraping = scraper.scrapear_sitio()
        self.stdout.write(f"Scraping completado: {len(resultados_scraping)} páginas nuevas/actualizadas.")
        
        # 2. Procesar PDFs
        self.stdout.write("\n[2/3] Procesando PDFs...")
        pdf_service = PDFService()
        resultados_pdfs = pdf_service.descargar_y_procesar_pdfs()
        self.stdout.write(f"PDFs procesados: {len(resultados_pdfs)}")
        
        # 3. Verificar si hubo cambios significativos
        # Por ejemplo, contar cuántos registros se actualizaron o crearon
        total_cambios = len(resultados_scraping) + len(resultados_pdfs)
        
        if total_cambios > 0:
            self.stdout.write(f"\n[3/3] Hubo {total_cambios} cambios. Actualizando modelo...")
            updater = ModelUpdater()
            resultado = updater.actualizar_modelo()
            if resultado['success']:
                self.stdout.write(self.style.SUCCESS("✅ Modelo actualizado correctamente."))
            else:
                self.stdout.write(self.style.ERROR("❌ Error al actualizar modelo: " + resultado.get('error', '')))
        else:
            self.stdout.write("\n[3/3] No hubo cambios. No es necesario actualizar modelo.")
        
        self.stdout.write("\n=== PROCESO COMPLETADO ===")