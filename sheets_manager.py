import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
from datetime import datetime
import re
from thefuzz import process, fuzz


# Configuración de acceso a Google Sheets
# Necesitarás descargar el archivo JSON de credenciales de tu consola de Google Cloud
# y guardarlo como 'credentials.json' en la misma carpeta.
SCOPE = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
CREDS_FILE = 'credentials.json'

def get_client():
    """Conecta con Google Sheets usando las credenciales."""
    import os
    
    # 1. Intentar desde variable de entorno (Para Vercel)
    creds_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if creds_json:
        try:
            creds_dict = json.loads(creds_json)
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
            return gspread.authorize(creds)
        except Exception as e:
            print(f"❌ Error con la variable GOOGLE_SERVICE_ACCOUNT_JSON: {e}")

    # 2. Intentar desde archivo local
    try:
        if os.path.exists(CREDS_FILE):
            creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, SCOPE)
            client = gspread.authorize(creds)
            return client
    except Exception as e:
        print(f"❌ Error conectando a Google Sheets: {e}")
    
    return None

def registrar_consulta_en_sheet(sheet_name, datos_paciente, datos_ai):
    """
    Escribe los datos de la consulta en la pestaña 'Consultas'.
    
    Args:
        sheet_name (str): Nombre de tu Google Sheet (ej: "Veterinaria_DB").
        datos_paciente (dict): Info básica (Nombre, Dueño ID) que viene de AppSheet.
        datos_ai (dict): El JSON generado por Gemini.
    """
    client = get_client()
    if not client:
        return False

    try:
        try:
            sheet = client.open(sheet_name)
        except:
            # Si falla por nombre, intentamos por ID
            sheet = client.open_by_key(sheet_name)
            
        worksheet = sheet.worksheet("Consultas")
        
        # Preparar la fila a insertar
        # Orden de columnas asumido:
        # Fecha | Paciente | Diagnóstico | Tratamiento | Costo Total | Resumen Clínico | Próx. Cita
        
        tratamiento_resumen = ", ".join([f"{m['medicamento']} ({m['dosis']})" for m in datos_ai.get('tratamiento', [])])
        
        fila = [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            datos_paciente.get('nombre_paciente', 'Desconocido'),
            datos_ai.get('diagnostico_presuntivo', 'Sin diagnóstico'),
            tratamiento_resumen,
            datos_ai.get('costos_estimados', {}).get('total', 0),
            datos_ai.get('resumen_clinico', ''),
            datos_ai.get('proxima_cita', '')
        ]
        
        worksheet.append_row(fila)
        print("✅ Consulta registrada exitosamente en Sheets.")
        
        # Actualizar Inventario
        actualizar_inventario(sheet, datos_ai.get('tratamiento', []))
        
        return True
    except Exception as e:
        print(f"❌ Error escribiendo en Sheets: {e}")
        return False

def actualizar_inventario(sheet_obj, lista_medicamentos):
    """
    Resta del inventario los medicamentos usados.
    Asume una pestaña 'Inventario' con columnas: Nombre | Stock
    """
    try:
        worksheet_inv = sheet_obj.worksheet("Inventario")
        # Obtenemos todos los datos del inventario para buscar con Inteligencia
        records = worksheet_inv.get_all_records()
        if not records:
            print("⚠️ El inventario está vacío.")
            return

        # Lista de nombres de medicamentos disponibles en el Excel
        # Asumimos que la primera columna se llama "Nombre" o "Medicamento"
        # Si no, usamos la primera llave disponible
        column_name = "Nombre" if "Nombre" in records[0] else list(records[0].keys())[0]
        nombres_inventario = [str(r[column_name]) for r in records]

        for med_recetado in lista_medicamentos:
            nombre_buscado = med_recetado.get('medicamento')
            if not nombre_buscado: continue

            # --- BUSQUEDA INTELIGENTE (FUZZY) ---
            # Busca la mejor coincidencia
            mejor_coincidencia, puntuacion = process.extractOne(nombre_buscado, nombres_inventario, scorer=fuzz.token_sort_ratio)
            
            print(f"🔍 Buscando '{nombre_buscado}'... Mejor coincidencia: '{mejor_coincidencia}' (Puntaje: {puntuacion})")

            if puntuacion >= 80: # Si la similitud es mayor al 80%
                # Encontrar la fila original (gspread usa base 1 y hay encabezado)
                # Buscamos el índice y sumamos 2 (1 por base 0 y 1 por el header)
                idx = nombres_inventario.index(mejor_coincidencia)
                row_idx = idx + 2
                
                # Leemos valor actual (Columna B / 2 suele ser stock)
                try:
                    current_stock = int(records[idx].get("Stock", records[idx].get("Existencias", list(records[idx].values())[1])))
                except:
                    # Fallback si no encuentra por nombre de columna
                    current_stock = int(worksheet_inv.cell(row_idx, 2).value)

                cantidad_usada = 1 
                qty_str = str(med_recetado.get('cantidad_a_dispensar', '1'))
                numbers = re.findall(r'\d+', qty_str)
                if numbers:
                    cantidad_usada = int(numbers[0])
                
                new_stock = current_stock - cantidad_usada
                worksheet_inv.update_cell(row_idx, 2, new_stock)
                print(f"📉 Stock actualizado para {mejor_coincidencia}: {current_stock} -> {new_stock}")
            else:
                print(f"⚠️ No se encontró una coincidencia clara para '{nombre_buscado}' (Puntaje más alto: {puntuacion}).")

                
    except Exception as e:
        print(f"❌ Error actualizando inventario: {e}")

def get_inventario(sheet_name):
    """Obtiene la lista completa de productos del inventario, filtrando filas vacías."""
    client = get_client()
    if not client:
        return []

    try:
        try:
            sheet = client.open(sheet_name)
        except:
            sheet = client.open_by_key(sheet_name)
            
        worksheet_inv = sheet.worksheet("Inventario")
        records = worksheet_inv.get_all_records()
        
        # Filtrar registros donde todas las columnas importantes estén vacías
        filtered_records = []
        for r in records:
            # Si al menos una columna tiene contenido, lo mantenemos
            values = [str(v).strip() for v in r.values()]
            if any(v and v != "0" and v != "0.0" for v in values):
                filtered_records.append(r)
                
        return filtered_records
    except Exception as e:
        print(f"❌ Error obteniendo inventario: {e}")
        return []

def agregar_item_inventario(sheet_name, item_data):
    """
    Agrega o actualiza un item en el inventario.
    item_data = {"nombre": "...", "cantidad": 10, "precio": 100}
    """
    client = get_client()
    if not client:
        return False

    try:
        try:
            sheet = client.open(sheet_name)
        except:
            sheet = client.open_by_key(sheet_name)
            
        worksheet_inv = sheet.worksheet("Inventario")
        records = worksheet_inv.get_all_records()
        
        nombre_nuevo = item_data.get('nombre')
        cantidad_nueva = int(item_data.get('cantidad', 0))
        precio_nuevo = item_data.get('precio', 0)
        
        # Identificar columnas (Nombre, Stock, Precio)
        # Fallback si no existen nombres exactos
        col_nombre = "Nombre" if records and "Nombre" in records[0] else "Medicamento"
        col_stock = "Stock" if records and "Stock" in records[0] else "Existencias"
        col_precio = "Precio" if records and "Precio" in records[0] else "Costo"

        # Refinar búsqueda de columnas por si tienen otros nombres o mayúsculas
        header = worksheet_inv.row_values(1)
        
        def find_header_match(possibles):
            for p in possibles:
                for h in header:
                    if p.lower() in h.lower().strip():
                        return h
            return header[0] if header else None

        col_nombre = find_header_match(["Nombre", "Medicamento", "Producto", "Item"]) or "Nombre"
        col_stock = find_header_match(["Stock", "Existencias", "Cantidad", "Cant"]) or "Stock"
        col_precio = find_header_match(["Precio", "Costo", "Valor"]) or "Precio"

        # Buscar si ya existe
        nombres_inventario = [str(r.get(col_nombre, "")) for r in records]
        
        mejor_coincidencia, puntuacion = process.extractOne(nombre_nuevo, nombres_inventario, scorer=fuzz.token_sort_ratio) if nombres_inventario else (None, 0)
        
        if puntuacion >= 95:
            # Actualizar existente
            idx = nombres_inventario.index(mejor_coincidencia)
            row_idx = idx + 2
            
            # Obtener stock actual
            current_stock = 0
            try:
                current_stock = int(records[idx].get(col_stock, 0))
            except: pass
            
            new_stock = current_stock + cantidad_nueva
            
            # gspread: encontrar índice de columna
            col_stock_idx = header.index(col_stock) + 1
            col_precio_idx = header.index(col_precio) + 1 if col_precio in header else None
            
            worksheet_inv.update_cell(row_idx, col_stock_idx, new_stock)
            if col_precio_idx:
                worksheet_inv.update_cell(row_idx, col_precio_idx, precio_nuevo)
                
            print(f"✅ Stock incrementado para {mejor_coincidencia}: {new_stock}")
        else:
            # Agregar nuevo
            nueva_fila = []
            for h in header:
                if h == col_nombre: nueva_fila.append(nombre_nuevo)
                elif h == col_stock: nueva_fila.append(cantidad_nueva)
                elif h == col_precio: nueva_fila.append(precio_nuevo)
                else: nueva_fila.append("")
            
            # Si el header estaba vacío o las columnas no coincidieron, asegurar al menos las 3 básicas
            if not nueva_fila or len(nueva_fila) < 1:
                nueva_fila = [nombre_nuevo, cantidad_nueva, precio_nuevo]

            worksheet_inv.append_row(nueva_fila)
            print(f"✅ Nuevo item agregado al inventario: {nombre_nuevo}")
            
        return True
    except Exception as e:
        print(f"❌ Error agregando al inventario: {e}")
        return False

def eliminar_item_inventario(sheet_name, nombre_item):
    """Elimina un item del inventario por su nombre."""
    client = get_client()
    if not client:
        return False

    try:
        try:
            sheet = client.open(sheet_name)
        except:
            sheet = client.open_by_key(sheet_name)
            
        worksheet_inv = sheet.worksheet("Inventario")
        records = worksheet_inv.get_all_records()
        
        # Identificar columna Nombre
        header = worksheet_inv.row_values(1)
        col_nombre = None
        possibles = ["Nombre", "Medicamento", "Producto", "Item"]
        for p in possibles:
            for h in header:
                if p.lower() in h.lower().strip():
                    col_nombre = h
                    break
            if col_nombre: break
            
        if not col_nombre:
            col_nombre = header[0]

        # Buscar el item
        nombres_inventario = [str(r.get(col_nombre, "")).strip() for r in records]
        
        # Primero intentar match exacto (sin importar mayúsculas)
        match_exacto = None
        for i, n in enumerate(nombres_inventario):
            if n.lower() == nombre_item.lower().strip():
                match_exacto = i
                break
        
        if match_exacto is not None:
            idx = match_exacto
            row_idx = idx + 2
            worksheet_inv.delete_rows(row_idx)
            print(f"🗑️ Item eliminado (Match Exacto): {nombres_inventario[idx]}")
            return True

        # Si no hay match exacto, usar fuzzy
        mejor_coincidencia, puntuacion = process.extractOne(nombre_item, nombres_inventario, scorer=fuzz.token_sort_ratio) if nombres_inventario else (None, 0)
        
        if puntuacion >= 80:
            idx = nombres_inventario.index(mejor_coincidencia)
            row_idx = idx + 2 # +1 base 0, +1 header
            worksheet_inv.delete_rows(row_idx)
            print(f"🗑️ Item eliminado (Fuzzy {puntuacion}%): {mejor_coincidencia}")
            return True
        else:
            print(f"⚠️ No se encontró una coincidencia clara para '{nombre_item}' (Puntaje: {puntuacion}).")
            return False
            
    except Exception as e:
        print(f"❌ Error eliminando del inventario: {e}")
        return False

def vaciar_inventario(sheet_name):
    """Elimina todos los registros del inventario excepto la cabecera."""
    client = get_client()
    if not client:
        return False

    try:
        try:
            sheet = client.open(sheet_name)
        except:
            sheet = client.open_by_key(sheet_name)
            
        worksheet_inv = sheet.worksheet("Inventario")
        # Mantener el header (fila 1), borrar desde la fila 2 hasta el final
        records = worksheet_inv.get_all_records()
        if records:
            # delete_rows(2, amount)
            worksheet_inv.delete_rows(2, len(records))
            print("🧹 Inventario vaciado correctamente.")
        return True
    except Exception as e:
        print(f"❌ Error al vaciar inventario: {e}")
        return False

# Prueba rápida
if __name__ == "__main__":
    # Necesitas credentials.json para correr esto
    print("Prueba de conexión (requiere credentials.json)...")
    # registrar_consulta_en_sheet("MiVeterinaria", {"nombre_paciente": "Firulais"}, {...datos_ai_simulados...})
