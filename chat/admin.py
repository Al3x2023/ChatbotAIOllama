# Register your models here.
from django.contrib import admin
from .models import ConocimientoUAEMEX, DocumentoPDF, Conversacion

admin.site.register(ConocimientoUAEMEX)
admin.site.register(DocumentoPDF)
admin.site.register(Conversacion)