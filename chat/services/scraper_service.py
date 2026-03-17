# chat/services/scraper_service.py (versión optimizada)

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from django.conf import settings
from chat.models import ConocimientoUAEMEX
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

logger = logging.getLogger(__name__)

class ScraperUAEMEX:
    def __init__(self):
        self.base_url = settings.UAEMEX_BASE_URL
        self.visited_urls = set()
        self.max_pages = 30
        self.palabras_clave = [
            'licenciatura', 'carrera', 'oferta-educativa', 'facultad',
            'admision', 'inscripcion', 'becas', 'contacto', 'historia',
            'mision', 'vision', 'calendario', 'convocatorias', 'programa',
            'plan de estudios', 'requisitos', 'perfil de ingreso'
        ]
        self.extensiones_ignorar = ('.pdf', '.jpg', '.jpeg', '.png', '.gif', 
                                     '.mp4', '.avi', '.mov', '.zip', '.rar')
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        self.timeout = 5  # Timeout reducido a 5 segundos

    def scrapear_sitio(self):
        """
        Versión ultra-rápida con ThreadPoolExecutor
        """
        print(f"🚀 Iniciando scraping ultrarrápido de {self.base_url}")
        resultados = []
        urls_por_visitar = [self.base_url]
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            
            while urls_por_visitar and len(self.visited_urls) < self.max_pages:
                url = urls_por_visitar.pop(0)
                
                if url in self.visited_urls or any(ext in url.lower() for ext in self.extensiones_ignorar):
                    continue
                
                self.visited_urls.add(url)
                
                # Lanzar tarea en hilo
                future = executor.submit(self._procesar_url, url)
                futures.append(future)
                
                # Si hay demasiadas tareas pendientes, esperar
                if len(futures) > 20:
                    for f in as_completed(futures[:10]):
                        result, nuevos_enlaces = f.result()
                        if result:
                            resultados.append(result)
                        if nuevos_enlaces:
                            urls_por_visitar.extend([u for u in nuevos_enlaces if u not in self.visited_urls])
                    futures = futures[10:]
            
            # Procesar tareas restantes
            for future in as_completed(futures):
                result, nuevos_enlaces = future.result()
                if result:
                    resultados.append(result)
                if nuevos_enlaces:
                    urls_por_visitar.extend([u for u in nuevos_enlaces if u not in self.visited_urls])
        
        print(f"✅ Scraping completado: {len(resultados)} páginas procesadas")
        return resultados

    def _procesar_url(self, url):
        """
        Procesa una URL individual (ejecutado en un hilo)
        """
        nuevos_enlaces = []
        resultado = None
        
        try:
            print(f"  → Procesando: {url[:80]}...")
            response = requests.get(url, timeout=self.timeout, headers=self.headers)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Extraer información
                info = self._extraer_informacion_rapida(soup, url)
                
                if info['contenido'] and len(info['contenido']) > 200:
                    conocimiento, creado = ConocimientoUAEMEX.objects.update_or_create(
                        fuente=url,
                        defaults={
                            'titulo': info['titulo'],
                            'contenido': info['contenido'][:5000],
                            'tipo': self._determinar_tipo(url, info['titulo'])
                        }
                    )
                    resultado = {'url': url, 'titulo': info['titulo'], 'creado': creado}
                    print(f"    ✅ Guardado: {info['titulo'][:50]}...")
                
                # Extraer enlaces
                nuevos_enlaces = self._extraer_enlaces_rapidos(soup, url)
                
        except requests.Timeout:
            print(f"    ⏱️ Timeout: {url[:50]}...")
        except Exception as e:
            print(f"    ❌ Error: {url[:50]}... - {str(e)[:50]}")
        
        return resultado, nuevos_enlaces

    def _extraer_informacion_rapida(self, soup, url):
        """
        Extrae información de forma ultra-rápida (solo lo esencial)
        """
        # Título
        titulo = soup.title.string if soup.title else url
        titulo = ' '.join(titulo.split())[:200]
        
        # Eliminar solo lo más pesado
        for elemento in soup(['script', 'style']):
            elemento.decompose()
        
        # Buscar contenido principal con selectores simples
        selectores = ['main', 'article', '.content', '#content', 'p']
        contenido = ""
        
        for selector in selectores:
            elementos = soup.select(selector)
            if elementos:
                textos = [e.get_text(strip=True) for e in elementos if len(e.get_text(strip=True)) > 50]
                if textos:
                    contenido = ' '.join(textos)[:10000]
                    break
        
        if not contenido:
            # Fallback rápido: primeros 20 párrafos
            parrafos = soup.find_all('p')[:20]
            contenido = ' '.join([p.get_text(strip=True) for p in parrafos if len(p.get_text(strip=True)) > 50])
        
        return {'titulo': titulo, 'contenido': contenido[:10000]}

    def _extraer_enlaces_rapidos(self, soup, url_actual):
        """
        Extrae enlaces de forma rápida (solo los más prometedores)
        """
        enlaces = []
        dominio_base = urlparse(self.base_url).netloc
        
        for link in soup.find_all('a', href=True)[:20]:  # Limitar a 20 enlaces por página
            href = link['href']
            url_completa = urljoin(url_actual, href)
            dominio_link = urlparse(url_completa).netloc
            
            if (dominio_link == dominio_base and 
                not any(ext in url_completa.lower() for ext in self.extensiones_ignorar) and
                len(url_completa) < 200):  # Ignorar URLs muy largas
                
                # Priorizar URLs con palabras clave
                if any(palabra in url_completa.lower() for palabra in self.palabras_clave):
                    enlaces.insert(0, url_completa)
                else:
                    enlaces.append(url_completa)
        
        return enlaces[:10]  # Máximo 10 enlaces por página

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