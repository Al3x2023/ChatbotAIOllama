import os

def cargar_urls_desde_archivo(ruta_archivo, max_lineas=None):
    """
    Lee un archivo de texto con una URL por línea y devuelve una lista.
    Si max_lineas está definido, solo toma esa cantidad.
    """
    if not os.path.exists(ruta_archivo):
        return []
    with open(ruta_archivo, 'r', encoding='utf-8') as f:
        lineas = f.readlines()
    urls = [linea.strip() for linea in lineas if linea.strip()]
    if max_lineas:
        urls = urls[:max_lineas]
    return urls

def eliminar_primeras_n_lineas(archivo, n):
    """
    Elimina las primeras n líneas del archivo (útil para quitar URLs ya procesadas).
    """
    if not os.path.exists(archivo):
        return
    with open(archivo, 'r', encoding='utf-8') as f:
        lineas = f.readlines()
    with open(archivo, 'w', encoding='utf-8') as f:
        f.writelines(lineas[n:])