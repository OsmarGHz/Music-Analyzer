import os
import argparse
import pandas as pd
import requests
import urllib3
import google.genai as genai
import lyricsgenius
from dotenv import load_dotenv

# Silenciar warnings de SSL cuando se usa verify=False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
# ============ FUNCIONES DE BÚSQUEDA DE LETRAS ============

def search_genius(artista, cancion):
    """
    Busca la letra de una canción en Genius.
    Retorna: (letra, encontrada, es_instrumental)
    - es_instrumental = True cuando la canción existe pero no tiene letra
    """
    try:
        # Temporalmente desactivar skip_non_songs para detectar instrumentales
        genius.skip_non_songs = False
        resultado = genius.search_song(cancion, artista)
        genius.skip_non_songs = True  # Restaurar
        
        if resultado:
            # Verificar si tiene letra real o es instrumental
            if resultado.lyrics and len(resultado.lyrics.strip()) > 50:
                return resultado.lyrics, True, False
            else:
                # Canción encontrada pero sin letra = instrumental
                return None, False, True
        else:
            return None, False, False
    except Exception as e:
        print(f"    ⚠️ Error en Genius: {e}")
        return None, False, False

def search_lrclib(artista, cancion):
    """
    Busca la letra de una canción en LRCLIB (lrclib.net).
    Retorna: (letra, encontrada)
    """
    headers = {
        "User-Agent": "Music-Analyzer/1.0 (https://github.com/OsmarGHz/Music-Analyzer)"
    }
    
    # Intentar primero con SSL, luego sin verificación si falla
    for verify_ssl in [True, False]:
        try:
            # Búsqueda exacta
            url = "https://lrclib.net/api/get"
            params = {
                "track_name": cancion,
                "artist_name": artista
            }
            
            response = requests.get(url, params=params, headers=headers, timeout=15, verify=verify_ssl)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("plainLyrics"):
                    return data["plainLyrics"], True
            
            # Búsqueda flexible
            url_search = "https://lrclib.net/api/search"
            params_search = {
                "track_name": cancion,
                "artist_name": artista
            }
            
            response = requests.get(url_search, params=params_search, headers=headers, timeout=15, verify=verify_ssl)
            
            if response.status_code == 200:
                data = response.json()
                if data and len(data) > 0 and data[0].get("plainLyrics"):
                    return data[0]["plainLyrics"], True
            
            return None, False
            
        except requests.exceptions.SSLError:
            if verify_ssl:
                # Reintentar sin verificación SSL
                continue
            else:
                return None, False
        except Exception as e:
            print(f"    Error en LRCLIB: {e}")
            return None, False
    
    return None, False

def search_song(artista, cancion):
    """
    Busca la letra de una canción en múltiples fuentes.
    Orden: 1) Genius, 2) LRCLIB
    Retorna: (letra, encontrada, fuente, es_instrumental)
    """
    # Intentar con Genius primero
    print(f"    🔍 Buscando en Genius...")
    letra, encontrada, es_instrumental = search_genius(artista, cancion)
    if encontrada:
        return letra, True, "Genius", False
    
    # Si es instrumental (detectado por Genius), retornar inmediatamente
    if es_instrumental:
        return None, False, None, True
    
    # Si no encuentra, intentar con LRCLIB
    print(f"    🔍 Buscando en LRCLIB...")
    letra, encontrada = search_lrclib(artista, cancion)
    if encontrada:
        return letra, True, "LRCLIB", False
    
    return None, False, None, False

def analyze_song(letra, artista, cancion, filtros):
    """
    Analiza la letra usando Gemini y los criterios del semáforo.
    Retorna: (clasificacion, motivos)
    """
    prompt = f"""
Analiza la siguiente letra de canción según los criterios del semáforo emocional.
IMPORTANTE: 
- Analiza, además de la letra proporcionada, el contexto de la canción (la intención del artista y otras cuestiones relevantes), y reseñas de la canción desde fuentes confiables.
- No busques otras versiones de la letra de la canción ni inventes contenido.

CRITERIOS DEL SEMÁFORO:
{filtros}

CANCIÓN: {cancion}
ARTISTA: {artista}

LETRA:
{letra}

Responde EXACTAMENTE en este formato (dos líneas separadas):
CLASIFICACION: [VERDE/AMARILLO/NARANJA/ROJO]
MOTIVOS: [Tu explicación aquí]
"""
    
    try:
        response = geminiai.models.generate_content(
            model="gemini-3-pro-preview",
            contents=prompt
        )
        return parse_answer(response.text)
    except Exception as e:
        return "ERROR", f"Error al analizar: {e}"

def analyze_instrumental(artista, cancion, filtros):
    """
    Analiza una canción instrumental usando Gemini.
    Retorna: (clasificacion, motivos)
    """
    prompt = f"""
Analiza la siguiente canción INSTRUMENTAL (sin letra) según los criterios del semáforo emocional.

IMPORTANTE: 
- Esta canción NO tiene letra, es completamente instrumental.
- Analiza el contexto de la canción: el estilo del artista, el álbum, el género musical, reseñas de la canción desde fuentes confiables.
- Considera si el artista o la canción tienen asociaciones problemáticas (violencia, contenido para adultos, etc.)
- Si es una canción instrumental de un artista que normalmente tiene contenido explícito, considera ese contexto.
- Las canciones instrumentales que son puramente musicales sin asociaciones problemáticas generalmente serían VERDE.

CRITERIOS DEL SEMÁFORO:
{filtros}

CANCIÓN: {cancion}
ARTISTA: {artista}

Responde EXACTAMENTE en este formato (dos líneas separadas):
CLASIFICACION: [VERDE/AMARILLO/NARANJA/ROJO]
MOTIVOS: [Tu explicación aquí, mencionando que es una canción instrumental y el contexto analizado]
"""
    
    try:
        response = geminiai.models.generate_content(
            model="gemini-3-pro-preview",
            contents=prompt
        )
        return parse_answer(response.text)
    except Exception as e:
        return "ERROR", f"Error al analizar: {e}"

def parse_answer(texto):
    """
    Separa la clasificación y los motivos de la respuesta de Gemini.
    Retorna: (clasificacion, motivos)
    """
    clasificacion = "PENDIENTE"
    motivos = texto
    
    # Buscar la clasificación
    for color in ["VERDE", "AMARILLO", "NARANJA", "ROJO"]:
        if color in texto.upper():
            clasificacion = color
            break
    
    # Extraer motivos (todo después de "MOTIVOS:" o la explicación)
    if "MOTIVOS:" in texto.upper():
        partes = texto.upper().split("MOTIVOS:")
        if len(partes) > 1:
            # Obtener el texto original después de MOTIVOS:
            idx = texto.upper().find("MOTIVOS:")
            motivos = texto[idx + 8:].strip()
    elif "CLASIFICACION:" in texto.upper():
        # Si tiene formato CLASIFICACION: X, quitar esa línea
        lineas = texto.split("\n")
        motivos_lineas = []
        for linea in lineas:
            if "CLASIFICACION:" not in linea.upper():
                motivos_lineas.append(linea)
        motivos = "\n".join(motivos_lineas).strip()
    
    return clasificacion, motivos

def select_file():
    parser = argparse.ArgumentParser(description='Analiza canciones usando el semáforo emocional')
    parser.add_argument('archivo', help='Ruta al archivo CSV con las canciones')
    args = parser.parse_args()
    
    if not os.path.exists(args.archivo):
        print(f"Error: El archivo '{args.archivo}' no existe")
        exit(1)
    
    return args.archivo


# ============ CONFIGURACIÓN ============
load_dotenv()

geminiai = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

genius = lyricsgenius.Genius(os.getenv("GENIUS_API_KEY"), timeout=30)
genius.verbose = True
genius.remove_section_headers = True
genius.skip_non_songs = True
genius.retries = 5

with open("filtros.txt", "r", encoding="utf-8") as archivo_filtros:
    filtros = archivo_filtros.read()

# Obtener archivo desde argumentos
archivo_csv = select_file()

# Intenta UTF-8 primero, si falla usa latin-1
try:
    dataframe = pd.read_csv(archivo_csv, encoding="utf-8")
except UnicodeDecodeError:
    dataframe = pd.read_csv(archivo_csv, encoding="latin-1")

print(f"Archivo: {archivo_csv}")

print(f"Canciones cargadas: {len(dataframe)}")

# ============ PROCESAR TODAS LAS CANCIONES ============
resultados = []
no_encontradas = []  # Lista para canciones sin letra
instrumentales = []  # Lista para canciones instrumentales

for index, cancion in dataframe.iterrows():
    track = cancion['Track name']
    artista = cancion['Artist name']
    
    print(f"\n[{index + 1}/{len(dataframe)}] {track} - {artista}")
    
    # Buscar letra
    letra, encontrada, fuente, es_instrumental = search_song(artista, track)
    
    if encontrada:
        print(f"  Letra encontrada en {fuente}")
        
        # Mostrar preview de la letra (primeras 8 líneas)
        lineas = [l for l in letra.split('\n') if l.strip()][:8]
        print(f"\n  --- Preview de la letra ---")
        for linea in lineas:
            print(f"  | {linea[:70]}{'...' if len(linea) > 70 else ''}")
        print(f"  ----------------------------")
        
        # Esperar confirmación del usuario
        respuesta = input(f"\n  [Enter]=Analizar | [s]=Skip | [m]=Manual | [i]=Instrumental | [q]=Salir: ").strip().lower()
        
        if respuesta == 'q':
            print("\n  Proceso terminado por el usuario.")
            break
        elif respuesta == 's':
            print(f"  Skipped por el usuario")
            no_encontradas.append(cancion.to_dict())
            continue
        elif respuesta == 'i':
            print(f"  Marcado como instrumental (VERDE)")
            instrumentales.append(cancion.to_dict())
            resultados.append({
                'Track name': track,
                'Artist name': artista,
                'Fuente letra': 'Instrumental',
                'Clasificación': 'VERDE',
                'Motivos': 'Canción instrumental sin letra.'
            })
            continue
        elif respuesta == 'm':
            print(f"\n  Ingresa la letra (termina con una linea vacia):")
            lineas_manual = []
            while True:
                linea = input()
                if linea == "":
                    break
                lineas_manual.append(linea)
            letra = "\n".join(lineas_manual)
            fuente = "Manual"
            print(f"  Letra manual recibida ({len(lineas_manual)} lineas)")
        
        print(f"  Analizando...")
        clasificacion, motivos = analyze_song(letra, artista, track, filtros)
        
        resultados.append({
            'Track name': track,
            'Artist name': artista,
            'Fuente letra': fuente,
            'Clasificación': clasificacion,
            'Motivos': motivos
        })
    elif es_instrumental:
        # Canción detectada como instrumental por Genius
        print(f"  🎵 Esta canción es instrumental (sin letra)")
        respuesta = input(f"  [Enter]=Analizar instrumental con Gemini | [v]=Verde directo | [s]=Skip | [q]=Salir: ").strip().lower()
        
        if respuesta == 'q':
            print("\n  Proceso terminado por el usuario.")
            break
        elif respuesta == 's':
            print(f"  Skipped por el usuario")
            no_encontradas.append(cancion.to_dict())
            continue
        elif respuesta == 'v':
            print(f"  Marcado como instrumental (VERDE)")
            instrumentales.append(cancion.to_dict())
            resultados.append({
                'Track name': track,
                'Artist name': artista,
                'Fuente letra': 'Instrumental',
                'Clasificación': 'VERDE',
                'Motivos': 'Canción instrumental sin letra.'
            })
        else:
            # Analizar instrumental con Gemini (sin letra)
            print(f"  Analizando instrumental con Gemini...")
            clasificacion, motivos = analyze_instrumental(artista, track, filtros)
            instrumentales.append(cancion.to_dict())
            resultados.append({
                'Track name': track,
                'Artist name': artista,
                'Fuente letra': 'Instrumental',
                'Clasificación': clasificacion,
                'Motivos': motivos
            })
    else:
        print(f"  Letra no encontrada en ninguna fuente")
        respuesta = input(f"  [m]=Ingresar manual | [i]=Instrumental | [s]=Skip | [q]=Salir: ").strip().lower()
        
        if respuesta == 'q':
            print("\n  Proceso terminado por el usuario.")
            break
        elif respuesta == 'm':
            print(f"\n  Ingresa la letra (termina con una linea vacia):")
            lineas_manual = []
            while True:
                linea = input()
                if linea == "":
                    break
                lineas_manual.append(linea)
            letra = "\n".join(lineas_manual)
            fuente = "Manual"
            print(f"  Letra manual recibida ({len(lineas_manual)} lineas)")
            
            print(f"  Analizando...")
            clasificacion, motivos = analyze_song(letra, artista, track, filtros)
            
            resultados.append({
                'Track name': track,
                'Artist name': artista,
                'Fuente letra': fuente,
                'Clasificación': clasificacion,
                'Motivos': motivos
            })
        elif respuesta == 'i':
            print(f"  Marcado como instrumental (VERDE)")
            instrumentales.append(cancion.to_dict())
            resultados.append({
                'Track name': track,
                'Artist name': artista,
                'Fuente letra': 'Instrumental',
                'Clasificación': 'VERDE',
                'Motivos': 'Canción instrumental sin letra.'
            })
        else:
            # Skip por defecto
            no_encontradas.append(cancion.to_dict())

# ============ GUARDAR RESULTADOS ============

# Mapeo de semáforo a nombre de playlist
PLAYLIST_NAMES = {
    'VERDE': 'Everything Green',
    'AMARILLO': 'Sentimental Zone',
    'NARANJA': 'Catchy But Careful',
    'ROJO': 'Banned Bangers'
}

# Obtener nombre base del archivo (sin extensión)
nombre_base = os.path.splitext(os.path.basename(archivo_csv))[0]

# --- Generar archivo .md con análisis detallado ---
archivo_md = f"{nombre_base}.md"
with open(archivo_md, 'w', encoding='utf-8') as f:
    f.write(f"# Análisis: {nombre_base}\n\n")
    f.write(f"Total de canciones analizadas: {len(resultados)}\n\n")
    f.write("| Canción | Artista | Semáforo | Motivos |\n")
    f.write("|---------|---------|----------|--------|\n")
    
    for r in resultados:
        # Escapar pipes en los motivos para no romper la tabla
        motivos_escaped = r['Motivos'].replace('|', '\\|').replace('\n', ' ')
        f.write(f"| {r['Track name']} | {r['Artist name']} | {r['Clasificación']} | {motivos_escaped} |\n")

print(f"\nAnálisis guardado → {archivo_md}")

# --- Generar archivo .csv para TuneMyMusic ---
# Crear lista con datos originales + playlist name según semáforo
csv_resultados = []
for index, cancion in dataframe.iterrows():
    track = cancion['Track name']
    artista = cancion['Artist name']
    
    # Buscar la clasificación de esta canción
    clasificacion = None
    for r in resultados:
        if r['Track name'] == track and r['Artist name'] == artista:
            clasificacion = r['Clasificación']
            break
    
    # Solo incluir si fue analizada
    if clasificacion and clasificacion in PLAYLIST_NAMES:
        csv_resultados.append({
            'Track name': track,
            'Artist name': artista,
            'Album': cancion.get('Album', ''),
            'Playlist name': PLAYLIST_NAMES[clasificacion],
            'Type': cancion.get('Type', ''),
            'ISRC': cancion.get('ISRC', ''),
            'Spotify - id': cancion.get('Spotify - id', '')
        })

archivo_csv_salida = f"{nombre_base}_clasificado.csv"
df_csv = pd.DataFrame(csv_resultados)
df_csv.to_csv(archivo_csv_salida, index=False, encoding="utf-8-sig")
print(f"CSV para TuneMyMusic → {archivo_csv_salida}")

# Guardar las no encontradas en CSV separado
if no_encontradas:
    df_pendientes = pd.DataFrame(no_encontradas)
    df_pendientes.to_csv(f"Sin_letra_{nombre_base}.csv", index=False, encoding="utf-8-sig")
    print(f"Sin letra: {len(no_encontradas)} canciones → Sin_letra_{nombre_base}.csv")

print(f"\n¡Listo! Analizadas: {len(resultados)} canciones")