import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
key = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=key)

try:
    print("Listando modelos disponibles...")
    for m in genai.list_models():
        print(f" - {m.name}")
except Exception as e:
    print(f"Error al listar: {e}")
