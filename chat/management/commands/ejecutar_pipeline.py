from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.core.cache import cache
from chat.services.model_updater import ModelUpdater
from chat.models import ConocimientoUAEMEX, DocumentoPDF
from django.db.models import Max


class Command(BaseCommand):
    help = "Ejecuta un ciclo completo de scraping, PDFs y actualización de modelo"

    def add_arguments(self, parser):
        parser.add_argument('--max-pages', type=int, default=120)
        parser.add_argument('--lote-html', type=int, default=300)
        parser.add_argument('--lote-pdf', type=int, default=150)
        parser.add_argument('--archivo-html', type=str, default='clasificadas/html_interesantes.txt')
        parser.add_argument('--archivo-pdf', type=str, default='clasificadas/pdfs_interesantes.txt')
        parser.add_argument('--consumir-archivos-clasificadas', action='store_true')
        parser.add_argument('--no-clasificadas', action='store_true')
        parser.add_argument('--skip-scraping', action='store_true')
        parser.add_argument('--skip-pdfs', action='store_true')
        parser.add_argument('--skip-model-update', action='store_true')
        parser.add_argument('--force-model-update', action='store_true')
        parser.add_argument('--lock-ttl', type=int, default=3600)

    def handle(self, *args, **options):
        lock_key = 'pipeline_lock'
        lock_ttl = options['lock_ttl']
        lock_set = cache.add(lock_key, '1', timeout=lock_ttl)
        if not lock_set:
            self.stdout.write(self.style.WARNING('Pipeline en ejecución, se omite este ciclo'))
            return

        conocimiento_antes = ConocimientoUAEMEX.objects.count()
        pdfs_antes = DocumentoPDF.objects.count()
        ultima_actualizacion_antes = ConocimientoUAEMEX.objects.aggregate(Max('fecha_actualizacion'))['fecha_actualizacion__max']
        hubo_errores = False
        uso_clasificadas = False
        try:
            if not options['no_clasificadas']:
                try:
                    self.stdout.write('Procesando URLs desde carpeta clasificadas...')
                    call_command(
                        'actualizar_auto',
                        lote_html=options['lote_html'],
                        lote_pdf=options['lote_pdf'],
                        archivo_html=options['archivo_html'],
                        archivo_pdf=options['archivo_pdf'],
                        consumir_archivos=options['consumir_archivos_clasificadas'],
                        skip_model_update=True
                    )
                    uso_clasificadas = True
                except Exception as exc:
                    hubo_errores = True
                    self.stdout.write(self.style.WARNING(f'Error en flujo clasificadas: {exc}'))

            if not uso_clasificadas:
                if not options['skip_scraping']:
                    self.stdout.write('Ejecutando scraping...')
                    try:
                        call_command('scrape_uaemex', max_pages=options['max_pages'])
                    except Exception as exc:
                        hubo_errores = True
                        self.stdout.write(self.style.WARNING(f'Error en scraping: {exc}'))
                else:
                    self.stdout.write('Scraping omitido')

                if not options['skip_pdfs']:
                    self.stdout.write('Procesando PDFs...')
                    try:
                        call_command('procesar_pdfs')
                    except Exception as exc:
                        hubo_errores = True
                        self.stdout.write(self.style.WARNING(f'Error en procesamiento de PDFs: {exc}'))
                else:
                    self.stdout.write('Procesamiento de PDFs omitido')

            if options['skip_model_update']:
                self.stdout.write('Actualización de modelo omitida')
                return

            conocimiento_despues = ConocimientoUAEMEX.objects.count()
            pdfs_despues = DocumentoPDF.objects.count()
            ultima_actualizacion_despues = ConocimientoUAEMEX.objects.aggregate(Max('fecha_actualizacion'))['fecha_actualizacion__max']
            hubo_cambios = (
                conocimiento_despues > conocimiento_antes or
                pdfs_despues > pdfs_antes or
                ultima_actualizacion_despues != ultima_actualizacion_antes
            )

            if hubo_cambios or options['force_model_update']:
                self.stdout.write('Actualizando modelo...')
                result = ModelUpdater().actualizar_modelo()
                if result.get('success'):
                    if hubo_errores:
                        self.stdout.write(self.style.WARNING('Pipeline completado con advertencias'))
                    else:
                        self.stdout.write(self.style.SUCCESS('Pipeline completado correctamente'))
                else:
                    error = result.get('error') or result.get('message') or 'Error desconocido'
                    self.stdout.write(self.style.ERROR(f'Error actualizando modelo: {error}'))
                    raise SystemExit(1)
            else:
                if hubo_errores:
                    self.stdout.write(self.style.WARNING('Pipeline finalizado con advertencias y sin actualización de modelo'))
                else:
                    self.stdout.write('Sin cambios detectados, no se actualiza modelo')
        finally:
            cache.delete(lock_key)
