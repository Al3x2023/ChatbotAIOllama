from django.core.management.base import BaseCommand
from chat.services.scraper_service import ScraperUAEMEX
from chat.utils.url_loader import cargar_urls_desde_archivo, eliminar_primeras_n_lineas
import os
from pathlib import Path

class Command(BaseCommand):
    help = 'Ejecuta el proceso automático de actualización con lotes de URLs externas'

    @staticmethod
    def _resolver_archivo(ruta_recibida, candidatos, tipo):
        if ruta_recibida and os.path.exists(ruta_recibida):
            if cargar_urls_desde_archivo(ruta_recibida, tipo=tipo):
                return ruta_recibida
        mejor_ruta = None
        mejor_cantidad = -1
        for ruta in candidatos:
            if os.path.exists(ruta):
                cantidad = len(cargar_urls_desde_archivo(ruta, tipo=tipo))
                if cantidad > mejor_cantidad:
                    mejor_cantidad = cantidad
                    mejor_ruta = ruta
        return mejor_ruta or ruta_recibida

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
            default='clasificadas/html_interesantes.txt',
            help='Ruta al archivo de URLs HTML'
        )
        parser.add_argument(
            '--archivo-pdf',
            type=str,
            default='clasificadas/pdfs_interesantes.txt',
            help='Ruta al archivo de URLs PDF'
        )
        parser.add_argument(
            '--skip-model-update',
            action='store_true',
            help='Omite actualización del modelo al final'
        )
        parser.add_argument(
            '--consumir-archivos',
            action='store_true',
            help='Elimina del archivo las URLs ya procesadas'
        )

    def handle(self, *args, **options):
        self.stdout.write("=== INICIANDO ACTUALIZACIÓN AUTOMÁTICA CON URLs EXTERNAS ===")
        
        base = Path.cwd() / 'clasificadas'
        ruta_html = self._resolver_archivo(
            options['archivo_html'],
            [
                str(base / 'html_interesantes.txt'),
                str(base / 'htmls_interesantes.txt'),
                str(base / 'html.txt')
            ],
            'html'
        )
        ruta_pdf = self._resolver_archivo(
            options['archivo_pdf'],
            [
                str(base / 'pdfs_interesantes.txt'),
                str(base / 'pdfs.txt')
            ],
            'pdf'
        )
        lote_html = options['lote_html']
        lote_pdf = options['lote_pdf']
        
        # Cargar URLs
        urls_html = cargar_urls_desde_archivo(ruta_html, tipo='html')
        urls_pdf = cargar_urls_desde_archivo(ruta_pdf, tipo='pdf')
        self.stdout.write(f"Archivo HTML usado: {ruta_html}")
        self.stdout.write(f"Archivo PDF usado: {ruta_pdf}")
        
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
            if options['consumir_archivos']:
                eliminar_primeras_n_lineas(ruta_html, len(lote_actual_html))
        else:
            self.stdout.write("\n[1/3] No hay URLs HTML para procesar.")
        
        # 2. Procesar PDFs
        if urls_pdf:
            lote_actual_pdf = urls_pdf[:lote_pdf]
            self.stdout.write(f"\n[2/3] Procesando lote de {len(lote_actual_pdf)} URLs PDF...")
            if lote_actual_pdf:
                try:
                    from chat.services.pdf_service import PDFService
                    pdf_service = PDFService(urls=lote_actual_pdf)
                    resultados_pdfs = pdf_service.descargar_y_procesar_pdfs()
                    self.stdout.write(f"PDFs procesados: {len(resultados_pdfs)}")
                    if options['consumir_archivos']:
                        eliminar_primeras_n_lineas(ruta_pdf, len(lote_actual_pdf))
                except ModuleNotFoundError as exc:
                    self.stdout.write(self.style.WARNING(f"No se pudo procesar PDFs por dependencia faltante: {exc}"))
            else:
                self.stdout.write("[2/3] Lote PDF en 0, se omite procesamiento.")
        else:
            self.stdout.write("\n[2/3] No hay URLs PDF para procesar.")
        
        # 3. Actualizar modelo si hubo cambios
        total_cambios = len(resultados_scraping) + len(resultados_pdfs)
        if options['skip_model_update']:
            self.stdout.write("\n[3/3] Actualización de modelo omitida por parámetro.")
        elif total_cambios > 0:
            self.stdout.write(f"\n[3/3] Hubo {total_cambios} cambios. Actualizando modelo...")
            from chat.services.model_updater import ModelUpdater
            updater = ModelUpdater()
            resultado = updater.actualizar_modelo()
            if resultado['success']:
                self.stdout.write(self.style.SUCCESS("✅ Modelo actualizado correctamente."))
            else:
                self.stdout.write(self.style.ERROR("❌ Error al actualizar modelo: " + resultado.get('error', '')))
        else:
            self.stdout.write("\n[3/3] No hubo cambios. No es necesario actualizar modelo.")
        
        self.stdout.write("\n=== PROCESO COMPLETADO ===")
