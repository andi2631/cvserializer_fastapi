from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import List, Optional
from langchain_community.chat_models import BedrockChat
from langchain_core.prompts import PromptTemplate
from langchain.output_parsers import PydanticOutputParser
from enum import Enum
import boto3
import os
import PyPDF2
import re
import time
from langsmith import Client

class EstadoEducacion(str, Enum):
    finalizado = 'finalizado'
    en_curso = 'en curso'
    incompleto = 'incompleto'

class TipoLink(str, Enum):
  linkedin = 'linkedin'
  github = 'github'
  portfolio = 'portfolio'
  website = 'website'
  other = 'other'


# FastAPI app
app = FastAPI()

# Setup Bedrock client
bedrock_runtime = boto3.client(
    service_name="bedrock-runtime",
    region_name="us-east-1",
)

# Configura el cliente de S3
s3 = boto3.client('s3')

# Configuración de LangSmith
LANGSMITH_API_KEY = "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"
os.environ["LANGCHAIN_API_KEY"] = LANGSMITH_API_KEY
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"
os.environ["LANGCHAIN_PROJECT"] = "pr-untimely-hydrocarb-12"

 

# LLM model
llm = BedrockChat(
    model_id="anthropic.claude-3-5-sonnet-20240620-v1:0",
    client=bedrock_runtime,
    model_kwargs={
        "max_tokens": 1500,
        "temperature": 0,
        "system": "Eres un asistente que extrae datos de CVs en formato texto. Siempre devuelves JSON estrictamente válido y completo, sin texto adicional. Sigue las reglas estrictamente."
    },
)

# Output schema
class Idioma(BaseModel):
    nombre: Optional[str] = None
    nivel: Optional[str] = None  # 'básico' | 'intermedio' | 'avanzado' | 'nativo'

class Educacion(BaseModel):
    institucion: Optional[str] = None
    titulo: Optional[str] = None
    fechaInicio: Optional[str] = None
    fechaFin: Optional[str] = None
    estado: Optional[EstadoEducacion] = None

class Experiencia(BaseModel):
    empresa: Optional[str] = None
    rol: Optional[str] = None
    descripcion: Optional[str] = None
    tecnologias: Optional[List[str]] = None
    fechaInicio: Optional[str] = None
    fechaFin: Optional[str] = None

class Certificacion(BaseModel):
    nombre: Optional[str] = None
    entidad: Optional[str] = None
 
class Link(BaseModel):
  url: Optional[str] = None
  tipo: Optional[TipoLink] = None

class ExperienciaTecnología(BaseModel):
  nombreTecnologia: Optional[str] = None
  aniosExperiencia: Optional[int] = None

class Candidato(BaseModel):
    nombre: Optional[str] = None
    correo: Optional[str] = None
    telefono: Optional[str] = None
    pais: Optional[str] = None
    fechaNacimiento: Optional[str] = None
    resumen: Optional[str] = None
    habilidades: Optional[List[str]] = None
    idiomas: Optional[List[Idioma]] = None
    educacion: Optional[List[Educacion]] = None
    experiencia: Optional[List[Experiencia]] = None
    certificaciones: Optional[List[Certificacion]] = None
    links: Optional[List[Link]] = None
    experienciaTecnología: Optional[List[ExperienciaTecnología]] = None
 
    
parser = PydanticOutputParser(pydantic_object=Candidato)

prompt_template = PromptTemplate(
    template="""
Tu tarea es analizar un texto de CV y devolver SOLAMENTE un JSON ESTRICTAMENTE válido que contenga la siguiente información de la persona descrita en el texto:

{format_instructions}

📋 DESCRIPCIÓN DE CAMPOS:Y 
- nombre: Nombre completo de la persona
- correo: Dirección de correo electrónico
- telefono: Número de teléfono de contacto
- pais: País de residencia actual
- fechaNacimiento: Fecha de nacimiento en formato "Mes Año"
- resumen: Breve descripción profesional o resumen del CV. Debe ser en tercera persona y en un tono profesional. Describiendo objetivamente lo que hace la persona.
- habilidades: Lista de habilidades técnicas y blandas mencionadas en el CV
- idiomas: Lista de idiomas que domina, cada uno con nombre y nivel
- educacion: Lista de estudios formales, incluyendo institución, título, fechas y estado
- experiencia: Lista de experiencias laborales, incluyendo empresa, rol, descripción y tecnologías utilizadas
- certificaciones: Lista de certificaciones profesionales
- links: Enlaces relevantes (LinkedIn, GitHub, portfolio, etc.)
- experienciaTecnología: Lista de tecnologías con años de experiencia en cada una

⚠️ INSTRUCCIONES IMPORTANTES:
- No devuelvas ningún texto o explicación adicional. SOLO el JSON plano.
- Incluye sin falta todos los campos definidos en el esquema. Si algún campo no existe, devuelvelo como `null`.
- Las fechas deben tener el formato: `"Mes Año"` (ej: `"Marzo 2023"`) o `null`.
- Usa exactamente los siguientes valores posibles para el campo `estado` en educación: `finalizado`, `en curso`, `incompleto`.
- Los links deben tener `url` y el tipo especificado en el enum `TipoLink`.
- Los idiomas deben tener `nombre` y `nivel`. Usa `básico`, `intermedio`, `avanzado` o `nativo`.
- Dentro de la seccion experiencia, se nombran tecnologias. Las mismas son lenguajes de programacion, frameworks, herramientas, etc que se usaron en el trabajo.
- Si no hay experiencia en una tecnologia, no la incluyas en el JSON en la seccion de experienciaTecnología. Solo cuenta como experiencia si trabajó con la tecnologia.
- Para la seccion de experienciaTecnología, solo incluyas tecnologias que tengan experiencia y calcula cuantos años de experiencia tiene en cada una.

🧠 Ejemplo de interpretación:
- Si dice "Alianza Francesa – B1", infiere que el idioma es "Francés" y el nivel es "intermedio".
- Si dice "Fullstack developer desde Abril 2024 - presente", se espera que eso esté dentro de `experiencia`.

📌 TEXTO DEL CV:
====================
{text}
====================
""",
    input_variables=["text", "format_instructions"]
)
print(prompt_template)

# Descarga el archivo PDF desde S3

def download_pdf_from_s3(bucket_name: str, key: str, download_path: str):
    s3.download_file(bucket_name, key, download_path)

# Extrae texto del PDF

def extract_text_from_pdf(file_path: str) -> str:
    with open(file_path, 'rb') as file:
        reader = PyPDF2.PdfReader(file)
        text = ''
        for page in reader.pages:
            text += page.extract_text()
    return text

def clean_text(text: str) -> str:
    text = text.replace('\r', ' ').replace('\n', ' ')  # Unificar saltos de línea
    text = re.sub(r'\s{2,}', ' ', text)  # Reemplaza múltiples espacios por uno solo
    text = text.replace('–', '')  # Cambia guiones largos a normales
    text = text.replace('•', '')  # Opcional: cambiar bullets a guiones
    text = re.sub(r'(\w) -(\w)', r'\1-\2', text)  # Une palabras partidas por guiones mal puestos
    text = re.sub(r'(?<=\w) (?=\w)', lambda m: m.group() if m.group().isupper() else ' ', text)
    text = re.sub(r'\b([A-Z]) ([A-Z])\b', r'\1\2', text)  # Une letras sueltas que deberían estar juntas
    return text.strip()

@app.post("/process_cv_from_s3")
async def process_cv_from_s3():
    try:
        # ⏱️ Tiempo total
        total_start = time.time()

        # ⏱️ 1. Descargar desde S3
        start = time.time()
        bucket_name = "cv-bucket-upload"
        key = "cv_uploads/7ab57f6a-94c1-4924-8713-00b1d443b7c7-CvMichelKuza.pdf"
        download_path = "/tmp/temp_cv.pdf"
        download_pdf_from_s3(bucket_name, key, download_path)
        print("✅ PDF descargado en:", download_path, f"({time.time() - start:.2f} s)")

        # ⏱️ 2. Extraer texto del PDF
        start = time.time()
        text = extract_text_from_pdf(download_path)
        print("✅ Texto extraído del PDF", f"({time.time() - start:.2f} s)")

        # ⏱️ 3. Limpiar texto
        start = time.time()
        text = clean_text(text)
        print("✅ Texto limpiado", f"({time.time() - start:.2f} s)")

        # ⏱️ 4. Armar prompt
        start = time.time()
        prompt = prompt_template.format_prompt(
            text=text,
            format_instructions=parser.get_format_instructions(),
        )
        print("✅ Prompt generado", f"({time.time() - start:.2f} s)")

        # ⏱️ 5. Llamada a Claude
        start = time.time()
        response = llm.invoke(prompt.to_string())
        
        print("✅ Respuesta LLM recibida", f"({time.time() - start:.2f} s)")

        # ⏱️ 6. Parsear respuesta
        start = time.time()
        result = parser.parse(response.content)
        print("✅ JSON parseado correctamente", f"({time.time() - start:.2f} s)")

        # ⏱️ Total
        print("⏱️ Tiempo total:", f"{time.time() - total_start:.2f} segundos")

        return result.model_dump()

    except Exception as e:
        print("❌ Error durante el procesamiento:", str(e))
        raise HTTPException(status_code=500, detail=str(e))
