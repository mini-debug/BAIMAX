import os
import google.generativeai as genai
from dotenv import load_dotenv
import os

load_dotenv() 
apiKey = os.getenv("GEMINI_API_KEY")

genai.configure(api_key=apiKey)
model = genai.GenerativeModel("gemini-1.5-flash")

def query_gemini(prompt: str) -> str:
    response = model.generate_content(prompt)
    return response.text
