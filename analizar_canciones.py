import os
import argparse
import pandas as pd
import google.genai as genai
import lyricsgenius
from dotenv import load_dotenv

def search_song(artista, cancion):
    """
    Busca la letra de una canción en Genius.
    Retorna: (letra, encontrada)
    """
    try:
        resultado = genius.search_song(cancion, artista)
        if resultado:
            return resultado.lyrics, True
        else:
            return None, False
    except Exception as e:
        print(f"  ⚠️ Error buscando letra: {e}")
        return None, False

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

for index, cancion in dataframe.iterrows():
    track = cancion['Track name']
    artista = cancion['Artist name']
    
    print(f"\n[{index + 1}/{len(dataframe)}] {track} - {artista}")
    
    # Buscar letra
    letra, encontrada = search_song(artista, track)
    
    if encontrada:
        print(f"  Letra encontrada en Genius")
        print(f"  Analizando...")
        clasificacion, motivos = analyze_song(letra, artista, track, filtros)
        fuente = "Genius"
        
        resultados.append({
            'Track name': track,
            'Artist name': artista,
            'Fuente letra': fuente,
            'Clasificación': clasificacion,
            'Motivos': motivos
        })
    else:
        print(f"  Auto-skip: Letra no encontrada")
        # Guardar la fila completa del CSV original
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
    print(f"⚠️ Sin letra: {len(no_encontradas)} canciones → Sin_letra_{nombre_base}.csv")

print(f"\n🎉 ¡Listo! Analizadas: {len(resultados)} canciones")