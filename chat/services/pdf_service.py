import os
import hashlib
import logging
import requests
import PyPDF2
import pdfplumber  # opcional
from io import BytesIO
from chat.models import DocumentoPDF, ConocimientoUAEMEX
from django.core.files.base import ContentFile
from django.conf import settings
from tenacity import retry, stop_after_attempt, wait_fixed

logger = logging.getLogger(__name__)

class PDFService:
    def __init__(self, urls=None):
        self.pdf_urls = urls or settings.UAEMEX_PDF_URLS

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def _descargar(self, url):
        return requests.get(url, timeout=30)

    def descargar_y_procesar_pdfs(self):
        resultados = []
        vistos = set()
        for url in self.pdf_urls:
            if not url:
                continue
            url = str(url).strip().strip('`').strip('"').strip("'").strip('<>').strip()
            if not url:
                continue
            if url in vistos:
                continue
            vistos.add(url)
            if '.pdf' not in url.lower() and '/pdf/' not in url.lower() and 'bitstream' not in url.lower():
                resultados.append({'url': url, 'omitido': True, 'motivo': 'no_parece_pdf'})
                continue
            logger.info(f"Procesando PDF: {url}")
            try:
                response = self._descargar(url)
                if response.status_code != 200:
                    raise Exception(f"HTTP {response.status_code}")
                content_type = response.headers.get('Content-Type', '').lower()
                if 'pdf' not in content_type and not url.lower().endswith('.pdf'):
                    resultados.append({'url': url, 'omitido': True, 'motivo': f'content_type_no_pdf:{content_type or "desconocido"}'})
                    continue

                # Calcular hash del contenido
                contenido = response.content
                hash_actual = hashlib.md5(contenido).hexdigest()

                # Verificar si ya existe y si ha cambiado
                pdf_existente = DocumentoPDF.objects.filter(url_origen=url).first()
                if pdf_existente and pdf_existente.hash_contenido == hash_actual:
                    logger.info(f"  → PDF sin cambios, omitiendo")
                    # Aún así, agregamos al resultado para que el comando sepa que se procesó (sin cambios)
                    resultados.append({
                        'url': url,
                        'nombre': pdf_existente.nombre,
                        'cambio': False,
                        'tamaño': len(pdf_existente.contenido_texto) if pdf_existente.contenido_texto else 0
                    })
                    continue

                # Extraer texto (con fallback)
                texto = self._extraer_texto_seguro(contenido)

                # Guardar
                nombre_archivo = os.path.basename(url) or f"pdf_{len(resultados)}.pdf"
                pdf, creado = DocumentoPDF.objects.update_or_create(
                    url_origen=url,
                    defaults={
                        'nombre': nombre_archivo,
                        'contenido_texto': texto[:10000],
                        'hash_contenido': hash_actual,
                        'procesado': True
                    }
                )
                if not pdf.archivo:
                    pdf.archivo.save(nombre_archivo, ContentFile(contenido), save=True)

                # Guardar en conocimiento
                if texto:
                    tipo = self._determinar_tipo(url, texto)
                    ConocimientoUAEMEX.objects.update_or_create(
                        fuente=url,
                        defaults={
                            'titulo': f"PDF: {nombre_archivo}",
                            'contenido': texto[:5000],
                            'tipo': tipo
                        }
                    )

                resultados.append({
                    'url': url,
                    'nombre': nombre_archivo,
                    'cambio': not pdf_existente,
                    'tamaño': len(texto)   # <--- AÑADIDO
                })
                logger.info(f"  → Texto extraído: {len(texto)} caracteres")

            except Exception as e:
                logger.error(f"Error procesando PDF {url}: {e}")
                resultados.append({'url': url, 'error': str(e)})

        return resultados

    def _extraer_texto_seguro(self, contenido):
        # Intenta con PyPDF2, si falla con pdfplumber
        try:
            return self._extraer_texto_pypdf2(contenido)
        except:
            try:
                return self._extraer_texto_pdfplumber(contenido)
            except:
                return ""

    def _extraer_texto_pypdf2(self, contenido):
        texto = ""
        with BytesIO(contenido) as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    texto += page_text + "\n"
        return ' '.join(texto.split())[:20000]

    def _extraer_texto_pdfplumber(self, contenido):
        texto = ""
        with BytesIO(contenido) as f:
            with pdfplumber.open(f) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        texto += page_text + "\n"
        return ' '.join(texto.split())[:20000]

    def _determinar_tipo(self, url, texto):
        texto_completo = (url + " " + texto).lower()
        if 'reglamento' in texto_completo or 'normatividad' in texto_completo:
            return 'reglamento'
        if 'plan de estudios' in texto_completo or 'programa' in texto_completo:
            return 'academico'
        return 'general'
