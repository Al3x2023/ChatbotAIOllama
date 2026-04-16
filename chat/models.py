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
    # NUEVO CAMPO
    hash_contenido = models.CharField(max_length=64, blank=True, help_text="MD5 del contenido del PDF para detectar cambios")
    
    class Meta:
        db_table = 'documentos_pdf'
    
    def __str__(self):
        return self.nombre

# --- NUEVOS MODELOS PARA TABLAS EXISTENTES ---

class Categoria(models.Model):
    nombre = models.CharField(max_length=255)
    activo = models.IntegerField(default=1)
    
    class Meta:
        managed = False  # Evita que Django modifique la tabla existente
        db_table = 'categorias'
        
    def __str__(self):
        return self.nombre

class Pregunta(models.Model):
    categoria = models.ForeignKey(Categoria, on_delete=models.DO_NOTHING, db_column='categoria_id', null=True)
    pregunta = models.TextField()
    respuesta = models.TextField()

    class Meta:
        managed = False  # Evita que Django modifique la tabla existente
        db_table = 'preguntas'
        
    def __str__(self):
        return self.pregunta[:50]

# models.py - Añade al final del archivo

class MemoriaUsuario(models.Model):
    """Memoria persistente del usuario a través de múltiples sesiones"""
    user_id = models.CharField(max_length=100, db_index=True, unique=True, help_text="Identificador único del usuario (email o username)")
    nombre = models.CharField(max_length=200, blank=True)
    nivel_educativo = models.CharField(max_length=100, blank=True, choices=[
        ('licenciatura', 'Licenciatura'),
        ('posgrado', 'Posgrado'),
        ('preparatoria', 'Preparatoria'),
        ('otro', 'Otro'),
    ])
    intereses = models.JSONField(default=list, help_text="Carreras o temas de interés")
    preferencias = models.JSONField(default=dict, help_text="Preferencias del usuario")
    resumen_conversaciones = models.TextField(blank=True, help_text="Resumen comprimido de conversaciones")
    total_interacciones = models.IntegerField(default=0)
    ultima_interaccion = models.DateTimeField(auto_now=True)
    fecha_registro = models.DateTimeField(auto_now_add=True)
    activo = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'memoria_usuarios'
        indexes = [
            models.Index(fields=['user_id']),
            models.Index(fields=['ultima_interaccion']),
        ]
    
    def __str__(self):
        return f"{self.user_id} - {self.total_interacciones} interacciones"

class MemoriaContexto(models.Model):
    """Contexto de conversación para mantener el hilo"""
    session_id = models.CharField(max_length=100, db_index=True)
    user_id = models.CharField(max_length=100, db_index=True, null=True)
    resumen_contexto = models.TextField()
    ultimo_tema = models.CharField(max_length=200, blank=True)
    entidades_mencionadas = models.JSONField(default=list, help_text="Entidades importantes mencionadas")
    timestamp = models.DateTimeField(auto_now_add=True)
    expira_en = models.DateTimeField()
    
    class Meta:
        db_table = 'memoria_contextos'
        indexes = [
            models.Index(fields=['session_id', 'timestamp']),
            models.Index(fields=['expira_en']),
        ]
    
    @classmethod
    def limpiar_expirados(cls):
        """Limpia contextos expirados"""
        cls.objects.filter(expira_en__lt=timezone.now()).delete()

class ResumenConversacion(models.Model):
    """Resúmenes periódicos de conversaciones"""
    session_id = models.CharField(max_length=100, db_index=True)
    user_id = models.CharField(max_length=100, db_index=True, null=True)
    resumen = models.TextField()
    temas_principales = models.JSONField(default=list)
    preguntas_clave = models.JSONField(default=list)
    fecha_inicio = models.DateTimeField()
    fecha_fin = models.DateTimeField()
    importancia = models.FloatField(default=1.0)
    
    class Meta:
        db_table = 'resumen_conversaciones'
        ordering = ['-importancia', '-fecha_fin']
        indexes = [
            models.Index(fields=['session_id', 'fecha_fin']),
        ]

class PalabraClave(models.Model):
    """Palabras clave para búsqueda semántica rápida"""
    palabra = models.CharField(max_length=100, unique=True, db_index=True)
    frecuencia = models.IntegerField(default=1)
    temas_relacionados = models.JSONField(default=list)
    
    class Meta:
        db_table = 'palabras_clave'