# chat/services/scraper_service.py

import requests
import urllib3
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from django.conf import settings
from chat.models import ConocimientoUAEMEX
import time
import concurrent.futures
import logging

# Desactivar advertencias de certificados SSL (común en páginas .edu.mx)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

class ScraperUAEMEX:
    def __init__(self, urls_extra=None):
        self.base_url = settings.UAEMEX_BASE_URL
        self.urls_extra = [u for u in (urls_extra or []) if u]
        self.visited_urls = set()
        self.max_pages = settings.SCRAPER_MAX_PAGES
        self.palabras_clave = [
            'licenciatura', 'carrera', 'oferta-educativa', 'facultad',
            'admision', 'admisión', 'inscripcion', 'inscripción', 'becas', 'contacto', 'historia',
            'mision', 'vision', 'calendario', 'convocatorias', 'programa',
            'plan de estudios', 'requisitos', 'perfil de ingreso', 'nuevoingreso',
            'preinscripcion', 'preinscripción', 'examen', 'derechos'
        ]
        self.extensiones_ignorar = ('.pdf', '.jpg', '.jpeg', '.png', '.gif', 
                                     '.mp4', '.avi', '.mov', '.zip', '.rar')
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        self.timeout = 15 # Aumentado a 15s para páginas lentas de la universidad
        self.max_links_per_page = 80 # Límite de links útiles a extraer por página

    def scrapear_sitio(self):
        print(f"🚀 Iniciando scraping ultrarrápido de {self.base_url}")
        resultados = []
        urls_por_visitar = []
        
        for url in [self.base_url, *getattr(settings, 'UAEMEX_SEED_URLS', []), *self.urls_extra]:
            if url and url not in urls_por_visitar:
                urls_por_visitar.append(url)
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = set() 
            
            while (urls_por_visitar or futures) and len(self.visited_urls) < self.max_pages:
                while urls_por_visitar and len(futures) < 10 and len(self.visited_urls) < self.max_pages:
                    url = urls_por_visitar.pop(0)
                    if url in self.visited_urls or any(ext in url.lower() for ext in self.extensiones_ignorar):
                        continue
                    self.visited_urls.add(url)
                    futures.add(executor.submit(self._procesar_url, url))
                
                if futures:
                    done, futures = concurrent.futures.wait(futures, return_when=concurrent.futures.FIRST_COMPLETED)
                    for future in done:
                        result, nuevos_enlaces = future.result()
                        if result:
                            resultados.append(result)
                        if nuevos_enlaces:
                            urls_por_visitar.extend([u for u in nuevos_enlaces if u not in self.visited_urls])
        
        print(f"✅ Scraping completado: {len(resultados)} páginas procesadas")
        return resultados

    def _procesar_url(self, url):
        nuevos_enlaces = []
        resultado = None
        
        try:
            print(f"  → Procesando: {url[:80]}...")
            # IMPORTANTE: verify=False evita que el scraper se caiga si la UAEMex tiene mal su candado SSL
            response = requests.get(url, timeout=self.timeout, headers=self.headers, verify=False)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                info = self._extraer_informacion_rapida(soup, url)
                chunks = info.get('chunks', [])
                
                if chunks:
                    tipo_nuevo = self._determinar_tipo(url, info['titulo'])
                    for i, texto_parrafo in enumerate(chunks):
                        fuente_unica = f"{url}#parrafo-{i}"
                        ConocimientoUAEMEX.objects.update_or_create(
                            fuente=fuente_unica,
                            defaults={
                                'titulo': info['titulo'],
                                'contenido': texto_parrafo,
                                'tipo': tipo_nuevo
                            }
                        )
                        
                    resultado = {'url': url, 'titulo': info['titulo'], 'creado': True, 'actualizado': False}
                    print(f"    ✅ Guardado: {info['titulo'][:50]}... ({len(chunks)} fragmentos)")
                
                nuevos_enlaces = self._extraer_enlaces_rapidos(soup, url)
            else:
                print(f"    ⚠️ HTTP {response.status_code}: {url[:50]}")
                
        except requests.Timeout:
            print(f"    ⏱️ Timeout (lento): {url[:50]}...")
        except Exception as e:
            print(f"    ❌ Error ({type(e).__name__}): {url[:50]}...")
        
        return resultado, nuevos_enlaces

    def _extraer_informacion_rapida(self, soup, url):
        titulo = soup.title.string if soup.title else url
        titulo = ' '.join(titulo.split())[:200]
        
        for elemento in soup(['script', 'style', 'nav', 'footer', 'header', 'aside']):
            elemento.decompose()
        
        parrafos_limpios = []
        
        # Agregamos 'div' por si la web usa divs en lugar de párrafos <p>
        for elemento in soup.find_all(['p', 'li', 'div', 'section']):
            texto = elemento.get_text(separator=" ", strip=True)
            if 50 < len(texto) < 1500 and texto not in parrafos_limpios:
                if "{" not in texto and "function" not in texto: # Filtro anti-código
                    parrafos_limpios.append(texto)
        
        return {'titulo': titulo, 'chunks': parrafos_limpios}

    def _extraer_enlaces_rapidos(self, soup, url_actual):
        enlaces = []
        
        # EL ERROR ESTABA AQUÍ: Analizamos TODOS los links primero, no los cortamos
        for link in soup.find_all('a', href=True):
            href = link['href'].strip()
            
            # Evitar basura desde el inicio
            if href.startswith('#') or href.startswith('javascript:') or href.startswith('mailto:'):
                continue
                
            url_completa = urljoin(url_actual, href)
            dominio_link = urlparse(url_completa).netloc
            
            if ('uaemex.mx' in dominio_link and 
                not any(ext in url_completa.lower() for ext in self.extensiones_ignorar) and
                len(url_completa) < 200):  
                
                if any(palabra in url_completa.lower() for palabra in self.palabras_clave):
                    enlaces.insert(0, url_completa)
                else:
                    enlaces.append(url_completa)
        
        # Eliminar duplicados
        enlaces_unicos = list(dict.fromkeys(enlaces))
        
        # Ahora sí, retornamos solo la cantidad máxima permitida de links ÚTILES
        return enlaces_unicos[:self.max_links_per_page]

    def _determinar_tipo(self, url, titulo):
        texto = (url + " " + titulo).lower()
        if any(p in texto for p in ['facultad', 'escuela', 'centro']):
            return 'facultad'
        elif any(p in texto for p in ['carrera', 'licenciatura', 'oferta', 'programa']):
            return 'carrera'
        elif any(p in texto for p in ['contacto', 'directorio', 'teléfono', 'ubicación']):
            return 'contacto'
        elif any(p in texto for p in ['admision', 'inscripcion', 'registro', 'examen']):
            return 'admision'
        elif any(p in texto for p in ['beca', 'apoyo', 'financiamiento']):
            return 'becas'
        else:
            return 'general'