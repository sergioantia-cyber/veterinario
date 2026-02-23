from flask import Flask, request, jsonify, render_template
import os
import requests
import re
from aiohttp import FormData
from ai_engine import transcribir_audio, analizar_consulta
from sheets_manager import registrar_consulta_en_sheet, get_inventario, agregar_item_inventario, eliminar_item_inventario, vaciar_inventario

app = Flask(__name__, template_folder='templates')

def get_drive_direct_url(url):
    """Convierte URL de vista de Drive a descarga directa"""
    if "drive.google.com" in url:
        # Intenta extraer ID del patrón /d/ID/
        match = re.search(r'/d/([a-zA-Z0-9_-]+)', url)
        if match:
            file_id = match.group(1)
            return f'https://drive.google.com/uc?export=download&id={file_id}'
    return url

# Directorio temporal para audios
UPLOAD_FOLDER = 'temp_uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@app.route('/')
def home():
    return render_template('upload.html')

@app.route('/upload_audio', methods=['POST'])
def upload_audio_local():
    """
    Endpoint para subir archivo directamente desde el navegador (Frontend Local)
    """
    if 'audio' not in request.files:
        return jsonify({"error": "No audio file part"}), 400
    
    file = request.files['audio']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    # Guardar archivo
    local_filename = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(local_filename)
    
    # Procesar
    try:
        # 1. Transcribir
        print(f"🎤 Procesando archivo subido: {file.filename}")
        transcript = transcribir_audio(local_filename)
        
        if not transcript or "Error" in transcript:
             return jsonify({"error": f"Transcription failed: {transcript}"}), 500
        
        print(f"📝 Transcripción obtenida: {transcript[:100]}...") # Mostrar los primeros 100 caracteres

        # 2. Analizar AI
        datos_estructurados = analizar_consulta(transcript)
        
        # 3. Guardar en Sheets
        datos_paciente = {
            "nombre_paciente": request.form.get("paciente", "Paciente Web"),
            "dueno_id": request.form.get("dueno_id", "WebUser")
        }
        
        SHEET_NAME = os.getenv("Sheets_ID") or "Veterinaria_DB"
        from sheets_manager import registrar_consulta_en_sheet
        registrar_consulta_en_sheet(SHEET_NAME, datos_paciente, datos_estructurados)
        
        return jsonify({
            "status": "success",
            "data": datos_estructurados
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/webhook/consulta', methods=['POST'])
def procesar_consulta():
    """
    Endpoint principal que recibe la notificación de AppSheet/Drive
    cuando se sube un nuevo audio de consulta.
    """
    data = request.json
    print(f"📩 Webhook recibido: {data}")
    
    # 1. Obtener URL del audio (AppSheet suele enviar la URL o ID de Drive)
    # Suponemos que recibimos {"audio_url": "...", "paciente_id": "..."}
    audio_url = data.get('audio_url')
    if not audio_url:
        return jsonify({"error": "No audio_url provided"}), 400
    
    # 2. Descargar el audio temporalmente
    local_filename = os.path.join(UPLOAD_FOLDER, "temp_audio.mp3") 
    
    try:
        # Convertir URL de Drive si es necesario
        audio_url = get_drive_direct_url(audio_url)
        
        if audio_url.startswith("http"):
            print(f"⬇️ Descargando audio desde: {audio_url}")
            response = requests.get(audio_url)
            if response.status_code == 200:
                with open(local_filename, 'wb') as f:
                    f.write(response.content)
            else:
                 return jsonify({"error": f"Failed to download file: Status {response.status_code}"}), 400
        else:
            # Si es local (para pruebas)
             return jsonify({"error": "Invalid URL format"}), 400

    except Exception as e:
        return jsonify({"error": f"Error downloading file: {str(e)}"}), 500

    # 3. Transcribir
    transcript = transcribir_audio(local_filename)
    
    # --- MODO REAL ---
    if not transcript or "Error" in transcript:
         return jsonify({"error": f"Transcription failed: {transcript}"}), 500
    # -----------------
    
    # 4. Analizar con Gemini
    datos_estructurados = analizar_consulta(transcript)
    
    # 5. Guardar en Google Sheets
    # En un caso real, 'paciente_id' vendría en el request.json desde AppSheet
    datos_paciente = {
        "nombre_paciente": data.get("nombre_paciente", "Paciente Desconocido"),
        "dueno_id": data.get("dueno_id", "Unknown")
    }
    
    # Usar ID/Nombre desde .env o fallback
    SHEET_NAME = os.getenv("Sheets_ID") or "Veterinaria_DB" 
    
    from sheets_manager import registrar_consulta_en_sheet
    exito_sheet = registrar_consulta_en_sheet(SHEET_NAME, datos_paciente, datos_estructurados)
    
    status_msg = "success" if exito_sheet else "warning: sheets update failed"

    return jsonify({
        "status": status_msg,
        "transcript": transcript,
        "data": datos_estructurados
    })

@app.route('/inventory')
def inventory_panel():
    """Sirve el panel de inventario"""
    return render_template('inventory.html')

@app.route('/api/inventory', methods=['GET', 'POST'])
def api_inventory():
    SHEET_NAME = os.getenv("Sheets_ID") or "Veterinaria_DB"
    
    if request.method == 'GET':
        items = get_inventario(SHEET_NAME)
        return jsonify(items)
    
    if request.method == 'POST':
        data = request.json
        # data = {"nombre": "...", "cantidad": 10, "precio": 100}
        success = agregar_item_inventario(SHEET_NAME, data)
        if success:
            return jsonify({"status": "success", "message": "Item actualizado correctamente"})
        else:
            return jsonify({"status": "error", "message": "No se pudo actualizar el inventario"}), 500

@app.route('/api/inventory/delete', methods=['POST'])
def delete_inventory_item():
    data = request.json
    nombre = data.get('nombre')
    pin = data.get('pin')
    
    if pin != "0424":
        return jsonify({"status": "error", "message": "PIN de seguridad incorrecto"}), 403
        
    SHEET_NAME = os.getenv("Sheets_ID") or "Veterinaria_DB"
    success = eliminar_item_inventario(SHEET_NAME, nombre)
    
    if success:
        return jsonify({"status": "success", "message": f"'{nombre}' eliminado correctamente"})
    else:
        # Si llegamos aquí, puede ser que no se encontró o hubo un error de cuota
        return jsonify({
            "status": "error", 
            "message": "No se pudo eliminar el item. Verifica si el nombre es correcto o intenta de nuevo en unos segundos (límite de Google)."
        }), 400 # Cambiamos a 400 para evitar el mensaje genérico de 500 del navegador

@app.route('/api/inventory/clear', methods=['POST'])
def clear_inventory():
    data = request.json
    pin = data.get('pin')
    
    if pin != "0424":
        return jsonify({"status": "error", "message": "PIN de seguridad incorrecto"}), 403
        
    SHEET_NAME = os.getenv("Sheets_ID") or "Veterinaria_DB"
    success = vaciar_inventario(SHEET_NAME)
    
    if success:
        return jsonify({"status": "success", "message": "Inventario vaciado por completo"})
    else:
        return jsonify({
            "status": "error", 
            "message": "No se pudo vaciar el inventario. Es posible que hayas excedido el límite de peticiones de Google. Espera un momento."
        }), 400

if __name__ == '__main__':
    app.run(debug=True, port=5000)
