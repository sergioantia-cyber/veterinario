import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
key = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=key)

try:
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
    response = model.generate_content("Hola, responde con la palabra 'FUNCIONA'")
    print(f"Resultado: {response.text}")
except Exception as e:
    print(f"Error detectado: {e}")
