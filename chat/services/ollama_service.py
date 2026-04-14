import re
import requests
import json
import time
import unicodedata
from django.conf import settings
from django.core.cache import cache
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

class OllamaService:
    def __init__(self):
        self.base_url = settings.OLLAMA_URL
        self.model = settings.MODEL_NAME
        self.base_model = getattr(settings, 'BASE_MODEL', 'llama3.2:latest')
        self.cache_timeout = 60 * 15
        self.timeout = 60

    def consultar_con_historial(self, mensaje, historial=None, contexto=""):
        memoria = ""
        mensaje_busqueda = mensaje

        if historial and len(historial) > 0:
            for h in historial:
                pregunta = h.get('pregunta', '')
                respuesta = h.get('respuesta', '')[:200]
                memoria += f"Usuario: {pregunta}\nAsistente: {respuesta}\n"
            
            # MAGIA DE MEMORIA
            ultimo_tema = historial[-1].get('pregunta', '')
            mensaje_busqueda = f"{ultimo_tema} {mensaje}"

        return self.consultar(mensaje, mensaje_busqueda=mensaje_busqueda, contexto=contexto, historial_texto=memoria)

    def consultar(self, mensaje, mensaje_busqueda=None, contexto="", historial_texto="", session_id=None):
        if not mensaje_busqueda:
            mensaje_busqueda = mensaje

        if not contexto:
            contexto = self._busqueda_en_cascada(mensaje_busqueda)

        # === MODO RAYOS X ===
        print("\n" + "="*50)
        print("🔍 LO QUE OLLAMA ESTÁ LEYENDO DE TU BASE DE DATOS:")
        print(contexto if contexto else "Nada (Contexto vacío)")
        print("="*50 + "\n")

        prompt = self._construir_prompt_pro(mensaje, contexto, historial_texto)
        options = self._get_options_pro()

        try:
            respuesta = self._llamar_con_reintentos(prompt, options)
        except Exception as e:
            print(f"❌ Error crítico: {e}")
            respuesta = self._get_fallback_response_pro()

        return self._limpiar_respuesta(respuesta)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((requests.exceptions.Timeout, requests.exceptions.ConnectionError))
    )
    def _llamar_con_reintentos(self, prompt, options):
        start_time = time.time()
        response = requests.post(
            f"{self.base_url}/api/generate",
            json={"model": self.model, "prompt": prompt, "stream": False, "options": options},
            timeout=self.timeout,
            headers={'Connection': 'close'}
        )
        print(f"⏱️ Tiempo de respuesta Ollama: {(time.time() - start_time):.2f}s")
        if response.status_code == 200:
            try: return response.json().get('response', '')
            except: raise Exception("Respuesta no JSON")
        else: raise Exception(f"HTTP {response.status_code}")

    def _busqueda_en_cascada(self, mensaje_busqueda):
        from chat.models import ConocimientoUAEMEX, Pregunta
        from django.db.models import Q
        
        mensaje_limpio = ''.join((c for c in unicodedata.normalize('NFD', mensaje_busqueda) if unicodedata.category(c) != 'Mn'))
        mensaje_limpio = re.sub(r'[^\w\s]', ' ', mensaje_limpio.lower())
        palabras = mensaje_limpio.split()
        
        stop_words = {'para', 'como', 'cuales', 'cual', 'sobre', 'este', 'esta', 'todo', 'pero', 'nivel', 'los', 'las', 'son', 'del', 'que', 'una', 'uno', 'universidad', 'uaemex', 'uaem', 'quien', 'cuando', 'cuanto', 'donde', 'sabes', 'dime', 'informacion', 'exacto', 'exacta', 'nuevo', 'ingreso', 'tiene', 'hacer', 'hay', 'alguna', 'algun'}
        palabras_filtradas = [p for p in palabras if len(p) > 3 and p not in stop_words]
        palabras_filtradas = list(dict.fromkeys(palabras_filtradas))

        if not palabras_filtradas: return ""
        contexto_final = ""
        print(f"\n🧠 Motor de Búsqueda | Palabras evaluadas: {palabras_filtradas}")

        try:
            query_faq = Q()
            for palabra in palabras_filtradas:
                query_faq |= Q(pregunta__icontains=palabra) | Q(respuesta__icontains=palabra)
            preguntas_brutas = list(Pregunta.objects.filter(query_faq).distinct()[:20])

            query_doc = Q()
            for palabra in palabras_filtradas:
                query_doc |= Q(contenido__icontains=palabra) | Q(titulo__icontains=palabra)
            docs_brutos = list(ConocimientoUAEMEX.objects.filter(query_doc).distinct()[:20])

            def contar_coincidencias(texto):
                texto_limpio = re.sub(r'[^\w\s]', ' ', ''.join((c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')).lower())
                return sum(1 for p in palabras_filtradas if p in texto_limpio.split())

            preguntas_ordenadas = sorted(preguntas_brutas, key=lambda x: contar_coincidencias(x.pregunta + " " + x.respuesta), reverse=True)[:4]
            docs_ordenados = sorted(docs_brutos, key=lambda x: contar_coincidencias(x.titulo + " " + x.contenido), reverse=True)[:3]

            if preguntas_ordenadas:
                contexto_final += "=== PREGUNTAS FRECUENTES ===\n"
                for p in preguntas_ordenadas: contexto_final += f"P: {p.pregunta}\nR: {p.respuesta}\n\n"
            
            if docs_ordenados:
                contexto_final += "=== DOCUMENTOS OFICIALES ===\n"
                for c in docs_ordenados: contexto_final += f"[{c.titulo}]: {c.contenido}\n\n"

            print(f"✅ [Ranker] Base de datos enviando las {len(preguntas_ordenadas)} FAQs y {len(docs_ordenados)} Docs más relevantes.")
        except Exception as e:
            print(f"Error en buscador híbrido: {e}")

        return contexto_final[:4000]

    def _construir_prompt_pro(self, mensaje, contexto, historial):
        palabras_ingles = {'what', 'when', 'where', 'who', 'why', 'how', 'is', 'the', 'can', 'you'}
        mensaje_words = set(re.sub(r'[^\w\s]', ' ', mensaje.lower()).split())
        
        if mensaje_words.intersection(palabras_ingles):
            regla_idioma = "RESPOND IN ENGLISH."
            etiqueta_final = "ANSWER:"
        else:
            regla_idioma = "RESPONDE EN ESPAÑOL."
            etiqueta_final = "RESPUESTA:"

        historial_prompt = f"=== HISTORIAL DE LA CONVERSACIÓN ===\n{historial}\n" if historial else ""

        # AQUI ESTÁ EL CAMBIO CLAVE EN LA REGLA 2 Y 3
        prompt = f"""Eres el Asistente Oficial de la UAEMex. Eres formal, directo y experto.

{historial_prompt}
=== BASE DE CONOCIMIENTOS ===
{contexto if contexto else "No hay información."}

=== INSTRUCCIONES ===
1. Responde a la PREGUNTA ACTUAL del usuario usando SOLO la BASE DE CONOCIMIENTOS.
2. Si la base de conocimientos dice que un costo o dato "varía", "es diferente" o "depende de algo", REPRODUCE ESA INFORMACIÓN. No asumas que no tienes la respuesta solo porque no hay un número exacto.
3. SOLO si la BASE DE CONOCIMIENTOS no menciona en lo absoluto el tema, responde textualmente: "Lo siento, no tengo esta información en mi base de datos actual. Por favor, consulta un medio oficial."
4. NO INVENTES DATOS.
5. {regla_idioma}

PREGUNTA ACTUAL: {mensaje}
{etiqueta_final}"""
        return prompt

    def _get_options_pro(self): return {"temperature": 0.0, "top_p": 0.9, "max_tokens": 800}
    def _limpiar_respuesta(self, respuesta): return respuesta.strip() if respuesta else "Error."
    def _get_fallback_response_pro(self): return "Problema técnico."
    
    def verificar_estado_rapido(self):
        try: return requests.get(f"{self.base_url}/api/tags", timeout=2).status_code == 200
        except: return False
        
    def listar_modelos(self): return []