from django.core.management.base import BaseCommand
from chat.services.scraper_service import ScraperUAEMEX
from chat.services.pdf_service import PDFService
from chat.services.model_updater import ModelUpdater
from chat.utils.url_loader import cargar_urls_desde_archivo, eliminar_primeras_n_lineas
import os

class Command(BaseCommand):
    help = 'Ejecuta el proceso automático de actualización con lotes de URLs externas'

    def add_arguments(self, parser):
        parser.add_argument(
            '--lote-html',
            type=int,
            default=100,
            help='Número de URLs HTML a procesar en este lote'
        )
        parser.add_argument(
            '--lote-pdf',
            type=int,
            default=50,
            help='Número de URLs PDF a procesar en este lote'
        )
        parser.add_argument(
            '--archivo-html',
            type=str,
            default='clasificadas/htmls_interesantes.txt',
            help='Ruta al archivo de URLs HTML'
        )
        parser.add_argument(
            '--archivo-pdf',
            type=str,
            default='clasificadas/pdfs_interesantes.txt',
            help='Ruta al archivo de URLs PDF'
        )

    def handle(self, *args, **options):
        self.stdout.write("=== INICIANDO ACTUALIZACIÓN AUTOMÁTICA CON URLs EXTERNAS ===")
        
        ruta_html = options['archivo_html']
        ruta_pdf = options['archivo_pdf']
        lote_html = options['lote_html']
        lote_pdf = options['lote_pdf']
        
        # Cargar URLs
        urls_html = cargar_urls_desde_archivo(ruta_html)
        urls_pdf = cargar_urls_desde_archivo(ruta_pdf)
        
        self.stdout.write(f"Total HTML disponibles: {len(urls_html)}")
        self.stdout.write(f"Total PDF disponibles: {len(urls_pdf)}")
        
        resultados_scraping = []
        resultados_pdfs = []
        
        # 1. Procesar HTML
        if urls_html:
            lote_actual_html = urls_html[:lote_html]
            self.stdout.write(f"\n[1/3] Procesando lote de {len(lote_actual_html)} URLs HTML...")
            scraper = ScraperUAEMEX(urls_extra=lote_actual_html)
            resultados_scraping = scraper.scrapear_sitio()
            self.stdout.write(f"Scraping completado: {len(resultados_scraping)} páginas nuevas/actualizadas.")
            # Eliminar las URLs procesadas del archivo
            eliminar_primeras_n_lineas(ruta_html, len(lote_actual_html))
        else:
            self.stdout.write("\n[1/3] No hay URLs HTML para procesar.")
        
        # 2. Procesar PDFs
        if urls_pdf:
            lote_actual_pdf = urls_pdf[:lote_pdf]
            self.stdout.write(f"\n[2/3] Procesando lote de {len(lote_actual_pdf)} URLs PDF...")
            pdf_service = PDFService(urls=lote_actual_pdf)  # usa las URLs del lote
            resultados_pdfs = pdf_service.descargar_y_procesar_pdfs()
            self.stdout.write(f"PDFs procesados: {len(resultados_pdfs)}")
            eliminar_primeras_n_lineas(ruta_pdf, len(lote_actual_pdf))
        else:
            self.stdout.write("\n[2/3] No hay URLs PDF para procesar.")
        
        # 3. Actualizar modelo si hubo cambios
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