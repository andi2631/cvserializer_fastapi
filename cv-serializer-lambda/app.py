from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import List, Optional

from langchain_community.chat_models import BedrockChat
from langchain_core.prompts import PromptTemplate
from langchain.output_parsers import PydanticOutputParser
import boto3
import os


# FastAPI app
app = FastAPI()

# Setup Bedrock client
bedrock_runtime = boto3.client(
    service_name="bedrock-runtime",
    region_name="us-east-1",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
)

# LLM model
llm = BedrockChat(
    model_id="anthropic.claude-3-sonnet-20240229-v1:0",
    client=bedrock_runtime,
    model_kwargs={"max_tokens": 300, "temperature": 0.3}
)

# Output schema
class WorkExperience(BaseModel):
    company: str
    position: str
    startDate: str
    endDate: Optional[str] = None
    description: Optional[str] = None

class CVSchema(BaseModel):
    name: str
    countryOfBirth: str
    studies: str
    workExperience: List[WorkExperience]

parser = PydanticOutputParser(pydantic_object=CVSchema)

prompt_template = PromptTemplate.from_template("""
Extraé los siguientes datos de este currículum y devolvé un JSON válido exactamente con este formato:

{format_instructions}

Texto del CV:
\"\"\"
{text}
\"\"\"
""")

# Request input schema
class CVRequest(BaseModel):
    text: str

# Endpoint
@app.post("/process_cv")
async def process_cv(req: CVRequest):
    try:
        prompt = prompt_template.format_prompt(
            text=req.text,
            format_instructions=parser.get_format_instructions()
        )
        response = llm.invoke(prompt.to_string())
        result = parser.parse(response.content)
        return result.model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
