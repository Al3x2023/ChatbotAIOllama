import requests
import PyPDF2
import io
from chat.models import DocumentoPDF, ConocimientoUAEMEX
from django.core.files.base import ContentFile
from django.conf import settings
import os

class PDFService:
    def __init__(self):
        self.pdf_urls = settings.UAEMEX_PDF_URLS
    
    def descargar_y_procesar_pdfs(self):
        """
        Descarga PDFs desde las URLs configuradas
        """
        resultados = []
        
        for url in self.pdf_urls:
            if not url:  # Saltar URLs vacías
                continue
                
            print(f"Procesando PDF: {url}")
            
            try:
                # Verificar si ya existe
                pdf_existente = DocumentoPDF.objects.filter(url_origen=url).first()
                
                if pdf_existente and pdf_existente.procesado:
                    print(f"  → PDF ya procesado anteriormente")
                    continue
                
                # Descargar PDF
                response = requests.get(url, timeout=30)
                
                if response.status_code == 200:
                    # Extraer texto
                    texto = self._extraer_texto_pdf(response.content)
                    
                    # Obtener nombre del archivo
                    nombre_archivo = os.path.basename(url)
                    if not nombre_archivo.endswith('.pdf'):
                        nombre_archivo = f"documento_{len(resultados)}.pdf"
                    
                    # Guardar o actualizar en BD
                    pdf, creado = DocumentoPDF.objects.update_or_create(
                        url_origen=url,
                        defaults={
                            'nombre': nombre_archivo,
                            'contenido_texto': texto[:10000],  # Limitar tamaño
                            'procesado': True
                        }
                    )
                    
                    # Guardar archivo físico
                    if not pdf.archivo:
                        pdf.archivo.save(
                            nombre_archivo,
                            ContentFile(response.content),
                            save=True
                        )
                    
                    # También guardar como conocimiento
                    if texto:
                        ConocimientoUAEMEX.objects.update_or_create(
                            fuente=url,
                            defaults={
                                'titulo': f"PDF: {nombre_archivo}",
                                'contenido': texto[:5000],
                                'tipo': 'reglamento' if 'reglamento' in url.lower() else 'general'
                            }
                        )
                    
                    resultados.append({
                        'url': url,
                        'nombre': nombre_archivo,
                        'creado': creado,
                        'tamaño': len(texto)
                    })
                    
                    print(f"  → Texto extraído: {len(texto)} caracteres")
                    
            except Exception as e:
                print(f"Error procesando PDF {url}: {str(e)}")
                resultados.append({
                    'url': url,
                    'error': str(e)
                })
        
        return resultados
    
    def _extraer_texto_pdf(self, contenido_binario):
        """
        Extrae texto de un archivo PDF
        """
        texto = ""
        
        try:
            with io.BytesIO(contenido_binario) as archivo_pdf:
                lector = PyPDF2.PdfReader(archivo_pdf)
                
                for pagina in lector.pages:
                    texto_pagina = pagina.extract_text()
                    if texto_pagina:
                        texto += texto_pagina + "\n"
                        
        except Exception as e:
            print(f"Error extrayendo texto: {str(e)}")
        
        return ' '.join(texto.split())[:20000]  # Limpiar y limitar