"""
chat/services/memory_service.py

Servicio de memoria persistente y contexto continuo para el asistente UAEMex.
"""

import re
from datetime import timedelta
from collections import Counter

from django.db.models import Q
from django.core.cache import cache
from django.utils import timezone

from ..models import (
    Conversacion,
    MemoriaUsuario,
    MemoriaContexto,
    ResumenConversacion,
    PalabraClave,
)


class MemoriaPersistenteService:
    """Gestiona la memoria persistente y el contexto de conversación del usuario."""

    def __init__(self, session_id: str, user_id: str | None = None):
        self.session_id = session_id
        self.user_id = user_id or session_id
        self.memoria_usuario = self._cargar_o_crear_memoria()
        self.contexto_activo = self._cargar_contexto_activo()

    # -------------------------------------------------------------------------
    # Inicialización
    # -------------------------------------------------------------------------

    def _cargar_o_crear_memoria(self) -> MemoriaUsuario:
        memoria, created = MemoriaUsuario.objects.get_or_create(
            user_id=self.user_id,
            defaults={
                "intereses": [],
                "preferencias": {},
                "total_interacciones": 0,
            },
        )
        if not created:
            memoria.total_interacciones += 1
            memoria.save(update_fields=["total_interacciones", "ultima_interaccion"])
        return memoria

    def _cargar_contexto_activo(self) -> MemoriaContexto | None:
        """Carga el contexto de sesión vigente (no expirado)."""
        return (
            MemoriaContexto.objects.filter(
                session_id=self.session_id,
                expira_en__gt=timezone.now(),
            )
            .order_by("-timestamp")
            .first()
        )

    # -------------------------------------------------------------------------
    # Aprendizaje
    # -------------------------------------------------------------------------

    def aprender_de_conversacion(self, pregunta: str, respuesta: str) -> None:
        """Extrae y almacena información útil de un intercambio."""

        # 1. Información personal (nombre, nivel)
        info_personal = self._extraer_info_personal(pregunta)
        if info_personal:
            if "nombre" in info_personal:
                self.memoria_usuario.nombre = info_personal["nombre"]
            if "nivel" in info_personal:
                self.memoria_usuario.nivel_educativo = info_personal["nivel"]
            self.memoria_usuario.save(update_fields=["nombre", "nivel_educativo"])

        # 2. Intereses
        intereses_nuevos = self._identificar_intereses(pregunta, respuesta)
        intereses_actuales = set(self.memoria_usuario.intereses or [])
        intereses_actuales.update(intereses_nuevos)
        self.memoria_usuario.intereses = list(intereses_actuales)[:10]
        self.memoria_usuario.save(update_fields=["intereses"])

        # 3. Palabras clave globales
        self._actualizar_palabras_clave(pregunta)

        # 4. Generar resumen cada 10 interacciones
        if self.memoria_usuario.total_interacciones % 10 == 0:
            self._generar_resumen()

        # 5. Actualizar contexto de sesión
        self._actualizar_contexto(pregunta, respuesta)

    def _extraer_info_personal(self, texto: str) -> dict:
        info = {}
        patrones = {
            "nombre": r"(?:me llamo|mi nombre es|soy)\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)?)",
            "nivel": r"(?:estudio|estoy en|curso|voy en)\s+(licenciatura|posgrado|preparatoria|maestría|doctorado)",
        }
        for key, pattern in patrones.items():
            match = re.search(pattern, texto, re.IGNORECASE)
            if match:
                info[key] = match.group(1).strip()
        return info

    def _identificar_intereses(self, pregunta: str, respuesta: str) -> list:
        mapa = {
            "admision":     ["admision", "ingreso", "examen", "convocatoria", "preinscripcion"],
            "becas":        ["beca", "apoyo", "manutencion", "estimulo", "economico"],
            "carreras":     ["carrera", "licenciatura", "ingenieria", "plan de estudios"],
            "servicios":    ["biblioteca", "deportes", "cultura", "tutorias", "medico"],
            "tramites":     ["tramite", "procedimiento", "documento", "solicitud", "pago"],
            "instalaciones":["campus", "edificio", "laboratorio", "aula"],
            "calendario":   ["fechas", "plazos", "calendario", "periodo", "vacaciones"],
        }
        texto = f"{pregunta} {respuesta}".lower()
        return [interes for interes, palabras in mapa.items() if any(p in texto for p in palabras)]

    def _actualizar_palabras_clave(self, texto: str) -> None:
        palabras = re.findall(r"\b[a-záéíóúñ]{4,}\b", texto.lower())
        for palabra in palabras[:5]:
            obj, created = PalabraClave.objects.get_or_create(palabra=palabra)
            if not created:
                obj.frecuencia += 1
                obj.save(update_fields=["frecuencia"])

    def _actualizar_contexto(self, pregunta: str, respuesta: str) -> None:
        """Crea o actualiza el contexto de la sesión activa."""
        MemoriaContexto.limpiar_expirados()
        entidades = self._extraer_entidades(pregunta)
        expira = timezone.now() + timedelta(minutes=30)

        if self.contexto_activo:
            nuevo_resumen = (
                f"Última pregunta: {pregunta[:120]} | "
                f"Contexto previo: {self.contexto_activo.resumen_contexto[:200]}"
            )
            self.contexto_activo.resumen_contexto = nuevo_resumen[:500]
            if entidades:
                self.contexto_activo.ultimo_tema = entidades[0]
                entidades_set = set(self.contexto_activo.entidades_mencionadas or [])
                entidades_set.update(entidades[:3])
                self.contexto_activo.entidades_mencionadas = list(entidades_set)
            self.contexto_activo.expira_en = expira
            self.contexto_activo.save()
        else:
            self.contexto_activo = MemoriaContexto.objects.create(
                session_id=self.session_id,
                user_id=self.user_id,
                resumen_contexto=f"Última pregunta: {pregunta[:200]}",
                ultimo_tema=entidades[0] if entidades else "",
                entidades_mencionadas=entidades,
                expira_en=expira,
            )

    def _extraer_entidades(self, texto: str) -> list:
        patrones = {
            "facultad": r"(Facultad|Escuela)\s+de\s+([A-Za-záéíóúñ\s]{3,30})",
            "carrera":  r"(Licenciatura|Ingeniería)\s+en\s+([A-Za-záéíóúñ\s]{3,30})",
            "lugar":    r"(Campus|Edificio|Biblioteca|Laboratorio)\s+([A-Za-záéíóúñ\s]{3,20})",
        }
        entidades = []
        for tipo, patron in patrones.items():
            for match in re.findall(patron, texto, re.IGNORECASE):
                entidades.append(f"{tipo}:{match[-1].strip()}")
        return entidades[:5]

    def _generar_resumen(self) -> None:
        """Genera y guarda un resumen de las últimas conversaciones."""
        conversaciones = list(
            Conversacion.objects.filter(session_id=self.session_id)
            .order_by("fecha")[:20]
        )

        if len(conversaciones) < 5:
            return

        todas_preguntas = " ".join(c.pregunta for c in conversaciones)
        palabras = re.findall(r"\b[a-záéíóúñ]{4,}\b", todas_preguntas.lower())
        temas = [p for p, _ in Counter(palabras).most_common(5)]

        resumen_texto = (
            f"Resumen de {len(conversaciones)} conversaciones. "
            f"Temas principales: {', '.join(temas)}."
        )

        ResumenConversacion.objects.create(
            session_id=self.session_id,
            user_id=self.user_id,
            resumen=resumen_texto,
            temas_principales=temas,
            preguntas_clave=[c.pregunta[:100] for c in conversaciones[:3]],
            fecha_inicio=conversaciones[0].fecha,
            fecha_fin=conversaciones[-1].fecha,
            importancia=1.0,
        )

        self.memoria_usuario.resumen_conversaciones = resumen_texto[:500]
        self.memoria_usuario.save(update_fields=["resumen_conversaciones"])

    # -------------------------------------------------------------------------
    # Recuperación de contexto
    # -------------------------------------------------------------------------

    def obtener_contexto_completo(self, pregunta_actual: str) -> dict:
        """Devuelve un diccionario con toda la información de memoria disponible."""
        contexto: dict = {
            "info_usuario": {},
            "historial_relevante": [],
            "intereses": [],
            "contexto_reciente": "",
            "entidades": [],
        }

        if self.memoria_usuario.nombre:
            contexto["info_usuario"]["nombre"] = self.memoria_usuario.nombre
        if self.memoria_usuario.nivel_educativo:
            contexto["info_usuario"]["nivel"] = self.memoria_usuario.nivel_educativo

        contexto["intereses"] = (self.memoria_usuario.intereses or [])[:5]

        if self.contexto_activo:
            contexto["contexto_reciente"] = self.contexto_activo.resumen_contexto
            contexto["entidades"] = (self.contexto_activo.entidades_mencionadas or [])[:3]

        resumenes = ResumenConversacion.objects.filter(
            Q(session_id=self.session_id) | Q(user_id=self.user_id)
        ).order_by("-importancia", "-fecha_fin")[:3]

        contexto["historial_relevante"] = [r.resumen for r in resumenes]

        return contexto

    def construir_prompt_con_memoria(self, pregunta: str, contexto_base: str) -> str:
        """
        Devuelve un bloque de texto con la memoria del usuario listo para
        ser antepuesto al contexto de la base de conocimiento.
        """
        mem = self.obtener_contexto_completo(pregunta)
        secciones: list[str] = []

        if mem["info_usuario"]:
            lineas = ["### INFORMACIÓN DEL USUARIO ###"]
            if "nombre" in mem["info_usuario"]:
                lineas.append(f"- Nombre: {mem['info_usuario']['nombre']}")
            if "nivel" in mem["info_usuario"]:
                lineas.append(f"- Nivel educativo: {mem['info_usuario']['nivel']}")
            secciones.append("\n".join(lineas))

        if mem["intereses"]:
            secciones.append(
                "### INTERESES PREVIOS DEL USUARIO ###\n"
                f"- Temas: {', '.join(mem['intereses'])}"
            )

        if mem["contexto_reciente"]:
            secciones.append(
                "### CONTEXTO DE SESIÓN ACTUAL ###\n"
                f"{mem['contexto_reciente']}"
            )

        if mem["historial_relevante"]:
            lineas = ["### RESÚMENES DE CONVERSACIONES ANTERIORES ###"]
            for resumen in mem["historial_relevante"][:2]:
                lineas.append(f"- {resumen[:200]}")
            secciones.append("\n".join(lineas))

        # Retornar string (nunca None)
        return "\n\n".join(secciones) if secciones else ""