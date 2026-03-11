import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from django.utils import timezone
from chat.models import ConocimientoUAEMEX

class Command(BaseCommand):
    help = 'Scrapea el sitio web de UAEMEX y actualiza la base de conocimientos'

    def handle(self, *args, **options):
        self.stdout.write('🕷️ Iniciando scraping de UAEMEX...')

        # Secciones: (palabra_clave, ruta, tipo)
        secciones = [
            ('carreras', '/oferta-educativa/licenciaturas', 'carrera'),
            ('licenciatura', '/oferta-educativa/licenciaturas', 'carrera'),
            ('facultades', '/oferta-educativa/centros-universitarios-y-unidades-academicas-profesionales-uaemex', 'facultad'),
            ('inscripcion', '/vida-universitaria/alumnos/control-escolar', 'general'),
            ('becas', '/vida-universitaria/alumnos/becas', 'general'),
            ('contacto', '/contacto', 'contacto'),
            ('historia', '/mi-universidad/bienvenido-a-la-uaemex/historia', 'general'),
            ('mision', '/mi-universidad/bienvenido-a-la-uaemex/mision-y-vision', 'general'),
            ('convocatorias', '/oferta-educativa/aspirantes/convocatorias-ingreso-2026', 'general'),
        ]

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

        for palabra_clave, ruta, tipo in secciones:
            url = f"https://www.uaemex.mx{ruta}"
            self.stdout.write(f"🔗 Procesando {url}...")

            try:
                response = requests.get(url, headers=headers, timeout=15)
                if response.status_code != 200:
                    self.stdout.write(self.style.ERROR(f"   ❌ Error HTTP {response.status_code}"))
                    continue

                soup = BeautifulSoup(response.text, 'html.parser')
                # Eliminar elementos no deseados
                for elem in soup(['script', 'style', 'nav', 'footer', 'header']):
                    elem.decompose()

                # Buscar contenido principal
                selectores = [
                    'main', 'article', '.content', '#content',
                    '.main-content', '.contenido-principal',
                    'div[class*="oferta"]', 'div[class*="licenciatura"]',
                    '.entry-content', '#primary'
                ]
                contenido_principal = None
                for selector in selectores:
                    contenido_principal = soup.select_one(selector)
                    if contenido_principal:
                        break

                if contenido_principal:
                    parrafos = contenido_principal.find_all('p')
                else:
                    parrafos = soup.find_all('p')

                # Extraer texto de párrafos con longitud significativa
                textos = []
                for p in parrafos:
                    texto = p.get_text(strip=True)
                    if len(texto) > 50:
                        textos.append(texto)

                if not textos:
                    # Fallback: todo el texto visible
                    textos = list(soup.stripped_strings)[:200]

                contenido = ' '.join(textos)[:5000]  # Limitar a 5000 caracteres
                titulo = soup.title.string.strip() if soup.title else f"Información sobre {palabra_clave}"
                titulo = titulo[:200]

                # Actualizar o crear registro (usando URL como identificador único)
                obj, created = ConocimientoUAEMEX.objects.update_or_create(
                    fuente=url,
                    defaults={
                        'titulo': titulo,
                        'contenido': contenido,
                        'tipo': tipo,
                        'fecha_actualizacion': timezone.now(),
                    }
                )
                if created:
                    self.stdout.write(self.style.SUCCESS(f"   ✅ Creado: {obj.titulo}"))
                else:
                    self.stdout.write(self.style.SUCCESS(f"   ✅ Actualizado: {obj.titulo}"))

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"   ❌ Error: {e}"))

        self.stdout.write(self.style.SUCCESS('🎉 Scraping completado.'))