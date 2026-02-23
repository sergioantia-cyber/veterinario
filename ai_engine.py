import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Configuración de APIs
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

if GOOGLE_API_KEY:
    # Limpieza agresiva de caracteres no deseados
    GOOGLE_API_KEY = "".join(c for c in GOOGLE_API_KEY if c.isalnum() or c in "-_")
    genai.configure(api_key=GOOGLE_API_KEY)
else:
    print("❌ ERROR: No se encontró GOOGLE_API_KEY en el archivo .env")

def transcribir_audio(audio_path):
    """
    Usa Google Gemini para transcribir el audio de la consulta.
    Retorna el texto transcrito.
    """
    if not GOOGLE_API_KEY:
         return "Error: No hay GOOGLE_API_KEY configurada."
    
    genai.configure(api_key=GOOGLE_API_KEY)
    print(f"🎤 Transcribiendo audio con Gemini: {audio_path}...")
    try:
        # Subir el archivo a Gemini (File API)
        audio_file = genai.upload_file(path=audio_path)
        
        # Esperar a que se procese si es necesario (generalmente rápido para audios cortos)
        import time
        while audio_file.state.name == "PROCESSING":
            time.sleep(1)
            audio_file = genai.get_file(audio_file.name)

        if audio_file.state.name == "FAILED":
            return "Error: El procesamiento del audio falló en Gemini."

        # Pedir la transcripción
        model = genai.GenerativeModel('gemini-flash-latest')
        response = model.generate_content([
            "Transcribe este audio de una consulta veterinaria exactamente palabra por palabra.",
            audio_file
        ])
        
        # Limpiar (opcional, buena práctica)
        # genai.delete_file(audio_file.name)
        
        return response.text
    except Exception as e:
        return f"Error en transcripción Gemini: {str(e)}"

def analizar_consulta(texto_transcrito):
    """
    Usa Google Gemini para analizar el texto y extraer datos estructurados.
    Retorna un JSON con Diagnóstico, Tratamiento, y Costos.
    """
    print("🧠 Analizando consulta con Gemini...")
    
    # Prompt de Sistema para definir la estructura JSON
    system_prompt = """
    Eres un asistente veterinario experto. Tu tarea es analizar la transcripción de una consulta veterinaria y extraer información estructurada en formato JSON estrictamente.
    
    El JSON debe tener esta estructura:
    {
        "resumen_clinico": "Breve resumen profesional del hallazgo (max 2 oraciones)",
        "diagnostico_presuntivo": "Nombre de la enfermedad o condición",
        "peso_paciente": "Si se menciona, o null",
        "temperatura": "Si se menciona, o null",
        "tratamiento": [
            {
                "medicamento": "Nombre comercial o genérico",
                "dosis": "Cantidad y frecuencia",
                "duracion": "Tiempo del tratamiento",
                "cantidad_a_dispensar": "Cantidad total para inventario (ej: 1 frasco, 10 tabletas)"
            }
        ],
        "procedimientos_realizados": ["Lista de inyecciones, limpieza, cirugía, etc."],
        "costos_estimados": {
            "consulta": 0.0,
            "procedimientos": 0.0,
            "medicamentos": 0.0,
            "total": 0.0
        },
        "recomendaciones_dueno": "Instrucciones claras para el propietario en lenguaje sencillo",
        "proxima_cita": "Fecha sugerida o 'A demanda'"
    }
    
    Si falta información (como precios exactos), estima basándote en el contexto o pon 0.0 si es imposible saber.
    Sé preciso con los nombres de medicamentos.
    """
    
    model = genai.GenerativeModel('gemini-flash-latest', generation_config={"response_mime_type": "application/json"})
    
    try:
        response = model.generate_content(f"{system_prompt}\n\nTRANSCRIPCIÓN:\n{texto_transcrito}")
        # Limpiamos la respuesta por si acaso trae markdown ```json ... ```
        texto_limpio = response.text.replace("```json", "").replace("```", "").strip()
        datos_json = json.loads(texto_limpio)
        print(f"✅ Análisis completado: {json.dumps(datos_json, indent=2, ensure_ascii=False)}")
        return datos_json
    except Exception as e:
        return {"error": f"Error en análisis de Gemini: {str(e)}"}

# Prueba rápida si se ejecuta directamente
if __name__ == "__main__":
    # Simulación
    print("----- MODO PRUEBA -----")
    ejemplo_texto = "El paciente Rufo presenta otitis externa en el oído derecho. Le aplicamos limpieza con Otoclean y se le receta Otomax, 5 gotas cada 12 horas por 7 días. El peso es de 15 kilos. Cobrar la consulta básica y la limpieza."
    resultado = analizar_consulta(ejemplo_texto)
    print(json.dumps(resultado, indent=2, ensure_ascii=False))
