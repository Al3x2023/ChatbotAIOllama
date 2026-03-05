from django.core.management.base import BaseCommand
from chat.services.scraper_service import ScraperUAEMEX

class Command(BaseCommand):
    help = 'Scrapea el sitio web de UAEMEX para obtener información'

    def add_arguments(self, parser):
        parser.add_argument(
            '--max-pages',
            type=int,
            default=50,
            help='Número máximo de páginas a scrapear'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Iniciando scraping de UAEMEX...'))
        
        scraper = ScraperUAEMEX()
        scraper.max_pages = options['max_pages']
        
        resultados = scraper.scrapear_sitio()
        
        self.stdout.write(
            self.style.SUCCESS(f'Scraping completado: {len(resultados)} páginas procesadas')
        )
        
        for resultado in resultados:
            status = "✅ CREADO" if resultado['creado'] else "🔄 ACTUALIZADO"
            self.stdout.write(f"  {status}: {resultado['titulo'][:50]}...")