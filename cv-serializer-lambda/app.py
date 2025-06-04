from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional, TypedDict
from langchain.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_community.chat_models import BedrockChat
from langgraph.graph import StateGraph, END
import boto3

app = FastAPI()

# ---------- Pydantic schemas ----------
class WorkExperience(BaseModel):
    company: str
    position: str
    startDate: str
    endDate: Optional[str] = ""
    description: Optional[str] = ""

class CVSchema(BaseModel):
    name: str
    countryOfBirth: Optional[str] = ""
    studies: str
    workExperience: List[WorkExperience]
    summary: Optional[str] = ""

class CVRequest(BaseModel):
    text: str

# ---------- LangGraph state ----------
class GraphState(TypedDict):
    text: str
    parsed: Optional[dict]
    retry_count: int

# ---------- LLM client ----------
bedrock_runtime = boto3.client("bedrock-runtime", region_name="us-east-1")
llm = BedrockChat(
    model_id="anthropic.claude-3-sonnet-20240229-v1:0",
    client=bedrock_runtime,
    model_kwargs={"max_tokens": 300, "temperature": 0.3},
)

# ---------- Prompt setup ----------
parser = PydanticOutputParser(pydantic_object=CVSchema)

prompt_template = PromptTemplate.from_template("""
Extraé los siguientes datos del currículum. Devolvé un JSON estrictamente válido con esta estructura:
El nombre del candidato es el nombre que aparece en el currículum.
El país de nacimiento es el país que aparece en el currículum.
El estudio es el estudio que aparece en el currículum.
El trabajo es el trabajo que aparece en el currículum.

{format_instructions}

✅ Reglas importantes:
- No devuelvas texto adicional, solo el JSON.
- Incluí todos los campos, aunque estén vacíos. Usá `null` o `""`.
- Fechas en formato "Mes Año".
- El campo countryOfBirth no debe omitirse.

Texto del CV:
{text}
""")

# ---------- LangGraph nodes ----------
def run_llm(state: GraphState) -> GraphState:
    prompt = prompt_template.format_prompt(
        text=state["text"],
        format_instructions=parser.get_format_instructions()
    )
    print(f"🔁 Reintento #{state['retry_count']}")
    response = llm.invoke(prompt.to_string())
    parsed = parser.parse(response.content)
    return {
        "text": state["text"],
        "parsed": parsed.model_dump(),
        "retry_count": state["retry_count"] + 1
    }

def needs_retry(state: GraphState) -> str:
    parsed = state["parsed"]
    if not parsed:
        return "retry" if state["retry_count"] < 1 else "end"

    required_fields = ["name", "countryOfBirth", "studies", "workExperience"]
    for field in required_fields:
        if not parsed.get(field):
            return "retry" if state["retry_count"] < 1 else "end"
    return "end"

# ---------- Build graph ----------
builder = StateGraph(GraphState)
builder.add_node("invoke_llm", run_llm)
builder.set_entry_point("invoke_llm")
builder.add_conditional_edges("invoke_llm", needs_retry, {
    "retry": "invoke_llm",
    "end": END,
})
graph = builder.compile()

# ---------- FastAPI endpoint ----------
@app.post("/process_cv")
async def process_cv(req: CVRequest):
    try:
        result = graph.invoke({
            "text": req.text,
            "parsed": None,
            "retry_count": 0
        })
        return result["parsed"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
