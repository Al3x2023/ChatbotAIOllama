from django.db import models
from django.utils import timezone

class Conversacion(models.Model):
    """Modelo para guardar las conversaciones del chat"""
    session_id = models.CharField(max_length=100, help_text="ID de sesión del usuario")
    pregunta = models.TextField()
    respuesta = models.TextField()
    fecha = models.DateTimeField(default=timezone.now)
    
    class Meta:
        db_table = 'conversaciones'
        ordering = ['-fecha']
    
    def __str__(self):
        return f"{self.fecha.strftime('%Y-%m-%d %H:%M')} - {self.pregunta[:50]}..."

class ConocimientoUAEMEX(models.Model):
    """Modelo para almacenar información de la UAEMEX (scraping)"""
    titulo = models.CharField(max_length=200)
    contenido = models.TextField()
    fuente = models.CharField(max_length=200, blank=True, unique=True)  # URL o documento
    tipo = models.CharField(max_length=50, choices=[
        ('facultad', 'Facultad'),
        ('carrera', 'Carrera'),
        ('reglamento', 'Reglamento'),
        ('contacto', 'Contacto'),
        ('general', 'Información General'),
    ], default='general')
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'conocimiento_uaemex'
        indexes = [
            models.Index(fields=['titulo']),
            models.Index(fields=['tipo']),
        ]
    
    def __str__(self):
        return self.titulo

class DocumentoPDF(models.Model):
    """Modelo para PDFs descargados"""
    nombre = models.CharField(max_length=200)
    archivo = models.FileField(upload_to='pdfs/', null=True, blank=True)
    url_origen = models.URLField()
    contenido_texto = models.TextField(blank=True)
    fecha_descarga = models.DateTimeField(auto_now_add=True)
    procesado = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'documentos_pdf'
    
    def __str__(self):
        return self.nombre