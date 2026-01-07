import os
import pandas as pd
import google.genai as genai
import lyricsgenius
from dotenv import load_dotenv

def buscar_letra(artista, cancion):
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

def analizar_cancion(letra, artista, cancion, filtros):
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
        return parsear_respuesta(response.text)
    except Exception as e:
        return "ERROR", f"Error al analizar: {e}"

def parsear_respuesta(texto):
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

# ============ CONFIGURACIÓN ============
load_dotenv()

geminiai = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

genius = lyricsgenius.Genius(os.getenv("GENIUS_API_KEY"))
genius.verbose = True
genius.remove_section_headers = True
genius.skip_non_songs = True

with open("filtros.txt", "r", encoding="utf-8") as archivo_filtros:
    filtros = archivo_filtros.read()

# Intenta UTF-8 primero, si falla usa latin-1
try:
    dataframe = pd.read_csv("Sentimental Zone.csv", encoding="utf-8")
except UnicodeDecodeError:
    dataframe = pd.read_csv("Sentimental Zone.csv", encoding="latin-1")

print(f"Canciones cargadas: {len(dataframe)}")

# ============ PROCESAR TODAS LAS CANCIONES ============
resultados = []
no_encontradas = []  # Lista para canciones sin letra

for index, cancion in dataframe.iterrows():
    track = cancion['Track name']
    artista = cancion['Artist name']
    
    print(f"\n[{index + 1}/{len(dataframe)}] {track} - {artista}")
    
    # Buscar letra
    letra, encontrada = buscar_letra(artista, track)
    
    if encontrada:
        print(f"  ✅ Letra encontrada en Genius")
        print(f"  🤖 Analizando...")
        clasificacion, motivos = analizar_cancion(letra, artista, track, filtros)
        fuente = "Genius"
        
        resultados.append({
            'Track name': track,
            'Artist name': artista,
            'Fuente letra': fuente,
            'Clasificación': clasificacion,
            'Motivos': motivos
        })
    else:
        print(f"  ⏭️ Auto-skip: Letra no encontrada")
        no_encontradas.append({
            'Track name': track,
            'Artist name': artista,
            'Album': cancion.get('Album', ''),
            'Spotify ID': cancion.get('Spotify - id', '')
        })

# ============ GUARDAR RESULTADOS ============
# Usar UTF-8 con BOM para que Excel lea bien los acentos
df_resultados = pd.DataFrame(resultados)
df_resultados.to_csv("Resultados.csv", index=False, encoding="utf-8-sig")
print(f"\n✅ Analizadas: {len(resultados)} canciones → Resultados.csv")

# Guardar las no encontradas en CSV separado
if no_encontradas:
    df_pendientes = pd.DataFrame(no_encontradas)
    df_pendientes.to_csv("Pendientes_sin_letra.csv", index=False, encoding="utf-8-sig")
    print(f"⚠️ Sin letra: {len(no_encontradas)} canciones → Pendientes_sin_letra.csv")

print(f"\n🎉 ¡Listo!")