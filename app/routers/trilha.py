from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
import os
import json
from openai import OpenAI

router = APIRouter()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))


class PerfilAluno(BaseModel):
    nome: str
    nivel: str
    horas_por_dia: float
    concurso_alvo: str
    data_concurso: Optional[str]
    materias_dominio: dict


@router.post("/gerar")
async def gerar_trilha(perfil: PerfilAluno):
    prompt = f"""
Você é um especialista em concursos públicos da Área Fiscal (SEFAZ, Receita Federal, Auditor).

Perfil do aluno:
- Nome: {perfil.nome}
- Nível: {perfil.nivel}
- Disponibilidade: {perfil.horas_por_dia}h por dia
- Concurso alvo: {perfil.concurso_alvo}
- Data prevista: {perfil.data_concurso or "não definida"}

Nível de domínio atual por matéria (0-100%):
{perfil.materias_dominio}

Monte uma trilha de estudos para as próximas 2 semanas.
Para cada dia liste: matéria de consumo, matéria de revisão, matéria de questões.
Priorize matérias com menor domínio e maior peso nos editais de Área Fiscal.

Responda APENAS em JSON:
{{
  "semana_1": [
    {{
      "dia": 1,
      "consumo": "nome da matéria",
      "revisao": "nome da matéria",
      "questoes": "nome da matéria",
      "justificativa": "breve explicação"
    }}
  ],
  "semana_2": [...]
}}
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )

    texto = response.choices[0].message.content

    try:
        trilha = json.loads(texto)
    except Exception:
        trilha = {"raw": texto}

    return {"trilha": trilha, "perfil": perfil.model_dump()}


@router.get("/status")
def status_trilha():
    if not os.getenv("OPENAI_API_KEY"):
        return {"status": "sem_chave", "mensagem": "Configure OPENAI_API_KEY no .env"}
    return {"status": "ok"}
