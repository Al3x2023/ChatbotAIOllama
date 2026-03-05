import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from django.conf import settings
from chat.models import ConocimientoUAEMEX
import time

class ScraperUAEMEX:
    def __init__(self):
        self.base_url = settings.UAEMEX_BASE_URL
        self.visited_urls = set()
        self.max_pages = 50  # Límite para no sobrecargar
    
    def scrapear_sitio(self):
        """
        Inicia el scraping desde la página principal
        """
        resultados = []
        urls_por_visitar = [self.base_url]
        
        print(f"Iniciando scraping de {self.base_url}")
        
        while urls_por_visitar and len(self.visited_urls) < self.max_pages:
            url = urls_por_visitar.pop(0)
            
            if url in self.visited_urls:
                continue
            
            print(f"Scrapeando: {url}")
            
            try:
                # Obtener página
                response = requests.get(url, timeout=10, headers={
                    'User-Agent': 'Mozilla/5.0 (compatible; ChatbotUAEMEX/1.0)'
                })
                
                if response.status_code == 200:
                    # Parsear HTML
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Extraer información
                    info = self._extraer_informacion(soup, url)
                    
                    if info['contenido']:
                        # Guardar en base de datos
                        conocimiento, creado = ConocimientoUAEMEX.objects.update_or_create(
                            fuente=url,
                            defaults={
                                'titulo': info['titulo'],
                                'contenido': info['contenido'][:5000],  # Limitar tamaño
                                'tipo': self._determinar_tipo(url, info['titulo'])
                            }
                        )
                        
                        resultados.append({
                            'url': url,
                            'titulo': info['titulo'],
                            'creado': creado
                        })
                        
                        print(f"  → Guardado: {info['titulo'][:50]}...")
                    
                    # Encontrar nuevos enlaces
                    nuevos_enlaces = self._extraer_enlaces(soup, url)
                    urls_por_visitar.extend(nuevos_enlaces)
                    
                    self.visited_urls.add(url)
                    
                    # Pequeña pausa para no saturar el servidor
                    time.sleep(1)
                    
            except Exception as e:
                print(f"Error scraping {url}: {str(e)}")
        
        return resultados
    
    def _extraer_informacion(self, soup, url):
        """
        Extrae el título y contenido principal de la página
        """
        # Título
        titulo = soup.title.string if soup.title else url
        titulo = ' '.join(titulo.split())[:200]
        
        # Eliminar elementos no deseados
        for elemento in soup(['script', 'style', 'nav', 'footer', 'header']):
            elemento.decompose()
        
        # Buscar contenido principal
        contenido = ""
        
        # Intentar encontrar el contenido principal
        main_content = soup.find('main') or soup.find('article') or soup.find('div', class_='content')
        
        if main_content:
            contenido = ' '.join(main_content.stripped_strings)
        else:
            # Si no hay contenedor específico, tomar todo el texto
            contenido = ' '.join(soup.stripped_strings)
        
        # Limpiar y limitar
        contenido = ' '.join(contenido.split())[:10000]
        
        return {
            'titulo': titulo,
            'contenido': contenido
        }
    
    def _extraer_enlaces(self, soup, url_actual):
        """
        Extrae enlaces válidos del mismo dominio
        """
        enlaces = []
        dominio_base = urlparse(self.base_url).netloc
        
        for link in soup.find_all('a', href=True):
            href = link['href']
            url_completa = urljoin(url_actual, href)
            dominio_link = urlparse(url_completa).netloc
            
            # Solo enlaces del mismo dominio y no visitados
            if (dominio_link == dominio_base and 
                url_completa not in self.visited_urls and
                not any(ext in url_completa for ext in ['.pdf', '.jpg', '.png', '.zip'])):
                
                enlaces.append(url_completa)
        
        return list(set(enlaces))[:10]  # Limitar a 10 enlaces por página
    
    def _determinar_tipo(self, url, titulo):
        """
        Determina el tipo de contenido basado en la URL y título
        """
        url_lower = url.lower()
        titulo_lower = titulo.lower()
        
        if 'facultad' in url_lower or 'facultad' in titulo_lower:
            return 'facultad'
        elif 'carrera' in url_lower or 'oferta' in url_lower:
            return 'carrera'
        elif 'reglamento' in url_lower or 'normatividad' in url_lower:
            return 'reglamento'
        elif 'contacto' in url_lower or 'directorio' in url_lower:
            return 'contacto'
        else:
            return 'general'