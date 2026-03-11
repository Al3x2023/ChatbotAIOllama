import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from django.conf import settings
from chat.models import ConocimientoUAEMEX
import time
import re

class ScraperUAEMEX:
    def __init__(self):
        self.base_url = settings.UAEMEX_BASE_URL
        self.visited_urls = set()
        self.max_pages = 50
        self.palabras_clave = [
            'licenciatura', 'carrera', 'oferta-educativa', 'facultad',
            'admision', 'inscripcion', 'becas', 'contacto', 'historia',
            'mision', 'vision', 'calendario', 'convocatorias', 'programa',
            'plan de estudios', 'requisitos', 'perfil de ingreso'
        ]
        # Extensiones de archivos a ignorar
        self.extensiones_ignorar = ('.pdf', '.jpg', '.jpeg', '.png', '.gif', '.svg', 
                                     '.mp4', '.avi', '.mov', '.zip', '.rar', '.7z',
                                     '.css', '.js', '.json', '.xml', '.ico')

    def scrapear_sitio(self):
        resultados = []
        urls_por_visitar = [self.base_url]
        print(f"Iniciando scraping de {self.base_url}")

        while urls_por_visitar and len(self.visited_urls) < self.max_pages:
            url = urls_por_visitar.pop(0)

            if url in self.visited_urls:
                continue

            # Ignorar URLs con extensiones de archivo
            if url.lower().endswith(self.extensiones_ignorar):
                print(f"Ignorando archivo: {url}")
                self.visited_urls.add(url)
                continue

            print(f"Scrapeando: {url}")

            try:
                response = requests.get(
                    url,
                    timeout=15,
                    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
                )
                response.encoding = 'utf-8'  # Forzar codificación

                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    info = self._extraer_informacion(soup, url)

                    # Solo guardar si el contenido es sustancial (> 500 caracteres y no es repetitivo)
                    if info['contenido'] and len(info['contenido']) > 500 and not self._es_repetitivo(info['contenido']):
                        conocimiento, creado = ConocimientoUAEMEX.objects.update_or_create(
                            fuente=url,
                            defaults={
                                'titulo': info['titulo'],
                                'contenido': info['contenido'][:5000],
                                'tipo': self._determinar_tipo(url, info['titulo'])
                            }
                        )
                        resultados.append({'url': url, 'titulo': info['titulo'], 'creado': creado})
                        print(f"  → Guardado: {info['titulo'][:50]}...")
                    else:
                        print(f"  → Contenido insuficiente o repetitivo, no guardado.")

                    nuevos_enlaces = self._extraer_enlaces(soup, url)
                    urls_por_visitar.extend(nuevos_enlaces)
                    self.visited_urls.add(url)
                    time.sleep(1)  # Ser amable con el servidor

            except requests.exceptions.Timeout:
                print(f"Timeout scraping {url}")
            except requests.exceptions.ConnectionError:
                print(f"Error de conexión en {url}")
            except Exception as e:
                print(f"Error scraping {url}: {str(e)}")

        return resultados

    def _extraer_informacion(self, soup, url):
        titulo = soup.title.string if soup.title else url
        titulo = ' '.join(titulo.split())[:200]

        # Eliminar elementos no deseados
        for elemento in soup(['script', 'style', 'nav', 'footer', 'header', 'aside']):
            elemento.decompose()

        # Selectores para contenido principal (priorizando los académicos)
        selectores = [
            'main', 'article', '.content', '#content',
            '.main-content', '.contenido-principal',
            'div[class*="oferta"]', 'div[class*="licenciatura"]',
            'div[class*="facultad"]', 'div[class*="carrera"]',
            '.entry-content', '.post-content', '#primary',
            'div[class*="programa"]', 'div[class*="plan"]',
            'section[class*="academica"]'
        ]

        contenido = ""
        main_content = None
        for selector in selectores:
            main_content = soup.select_one(selector)
            if main_content:
                break

        if main_content:
            contenido = ' '.join(main_content.stripped_strings)
        else:
            # Si no se encuentra un contenedor específico, tomar todos los párrafos
            parrafos = soup.find_all('p')
            contenido = ' '.join([p.get_text(strip=True) for p in parrafos if len(p.get_text(strip=True)) > 50])

        # Limpiar y limitar
        contenido = re.sub(r'\s+', ' ', contenido).strip()
        contenido = contenido[:10000]
        return {'titulo': titulo, 'contenido': contenido}

    def _es_repetitivo(self, texto):
        """
        Detecta si el texto es probablemente repetitivo (ej. páginas de galerías con frases cortas repetidas).
        """
        lineas = texto.split('\n')
        if len(lineas) > 10:
            # Verificar si hay muchas líneas iguales o muy similares
            lineas_unicas = set(lineas)
            if len(lineas_unicas) < len(lineas) * 0.3:  # Menos del 30% únicas
                return True
        return False

    def _extraer_enlaces(self, soup, url_actual):
        enlaces = []
        dominio_base = urlparse(self.base_url).netloc

        for link in soup.find_all('a', href=True):
            href = link['href']
            url_completa = urljoin(url_actual, href)
            dominio_link = urlparse(url_completa).netloc

            if (dominio_link == dominio_base and
                url_completa not in self.visited_urls and
                not url_completa.lower().endswith(self.extensiones_ignorar) and
                not self._es_enlace_irrelevante(url_completa)):

                if any(palabra in url_completa.lower() for palabra in self.palabras_clave):
                    enlaces.insert(0, url_completa)  # Priorizar
                else:
                    enlaces.append(url_completa)

        enlaces_unicos = list(dict.fromkeys(enlaces))[:20]
        return enlaces_unicos

    def _es_enlace_irrelevante(self, url):
        """
        Ignora enlaces que probablemente no contengan información útil (ej. secciones de galería, tags, etc.).
        """
        partes = urlparse(url).path.lower()
        irrelevantes = ['/tag/', '/category/', '/author/', '/page/', '/feed', '/xmlrpc', '/wp-', 'login', 'registro']
        return any(irr in partes for irr in irrelevantes)

    def _determinar_tipo(self, url, titulo):
        texto = (url + " " + titulo).lower()
        if any(p in texto for p in ['facultad', 'escuela', 'centro']):
            return 'facultad'
        elif any(p in texto for p in ['carrera', 'licenciatura', 'oferta', 'programa', 'plan']):
            return 'carrera'
        elif any(p in texto for p in ['reglamento', 'normatividad', 'ley', 'estatuto', 'legislacion']):
            return 'reglamento'
        elif any(p in texto for p in ['contacto', 'directorio', 'teléfono', 'ubicación', 'correo']):
            return 'contacto'
        elif any(p in texto for p in ['admision', 'inscripcion', 'registro', 'examen', 'convocatoria']):
            return 'admision'
        elif any(p in texto for p in ['beca', 'apoyo', 'financiamiento']):
            return 'becas'
        elif any(p in texto for p in ['historia', 'mision', 'vision', 'identidad', 'valores']):
            return 'institucional'
        else:
            return 'general'