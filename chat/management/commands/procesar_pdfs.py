from django.core.management.base import BaseCommand
from chat.services.pdf_service import PDFService

class Command(BaseCommand):
    help = 'Descarga y procesa PDFs de UAEMEX'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Iniciando procesamiento de PDFs...'))
        
        pdf_service = PDFService()
        resultados = pdf_service.descargar_y_procesar_pdfs()
        
        self.stdout.write(
            self.style.SUCCESS(f'Procesamiento completado: {len(resultados)} PDFs')
        )
        
        for resultado in resultados:
            if 'error' in resultado:
                self.stdout.write(self.style.ERROR(f"  ❌ ERROR: {resultado['url']}"))
            else:
                self.stdout.write(
                    self.style.SUCCESS(f"  ✅ {resultado['nombre']} - {resultado['tamaño']} caracteres")
                )