from ai_engine import transcribir_audio, analizar_consulta
from sheets_manager import registrar_consulta_en_sheet
import os
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURACIÓN ---
# Pon aquí el nombre EXACTO de tu archivo de audio (asegúrate de que esté en esta misma carpeta)
NOMBRE_ARCHIVO_AUDIO = "audio_consulta.mp3"  # <--- CAMBIA ESTO SI TU ARCHIVO TIENE OTRO NOMBRE
# ---------------------

if not os.path.exists(NOMBRE_ARCHIVO_AUDIO):
    print(f"\n❌ ERROR: No encuentro el archivo '{NOMBRE_ARCHIVO_AUDIO}' en la carpeta.")
    print(f"📂 Carpeta actual: {os.getcwd()}")
    print("👉 Por favor, pega tu archivo de audio aquí y asegúrate de que el nombre coincida en el script.")
else:
    print(f"🎤 1. Transcribiendo '{NOMBRE_ARCHIVO_AUDIO}'...")
    texto = transcribir_audio(NOMBRE_ARCHIVO_AUDIO)
    print("\n📝 Transcripción obtenida:")
    print("-" * 20)
    print(texto)
    print("-" * 20)
    
    if texto and "Error" not in texto:
        print("\n🧠 2. Analizando con Inteligencia Artificial...")
        datos = analizar_consulta(texto)
        print("\n📊 Datos estructurados:")
        import json
        print(json.dumps(datos, indent=2, ensure_ascii=False))
        
        print("\n💾 3. Guardando en Google Sheets...")
        SHEET_NAME = os.getenv("Sheets_ID") or "Veterinaria_DB"
        
        # Datos simulados del paciente (ya que no viene de la App)
        paciente = {
            "nombre_paciente": "Paciente de Prueba (Audio Local)",
            "dueno_id": "AdminLocal"
        }
        
        exito = registrar_consulta_en_sheet(SHEET_NAME, paciente, datos)
        if exito:
            print("\n✅ ¡ÉXITO! La consulta se ha guardado en tu Google Sheet.")
        else:
            print("\n⚠️ Hubo un problema al guardar en Sheets.")
    else:
        print("\n❌ Falló la transcripción. Revisa tu API Key de OpenAI.")
