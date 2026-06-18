from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, List

router = APIRouter()


class MateriaStatus(BaseModel):
    nome: str
    nivel_dominio: float     # 0-100
    status: str              # sem_pdf | consumo | revisao_parcial | revisao
    pdfs_subidos: int


class PerfilResponse(BaseModel):
    nome: str
    concurso_alvo: str
    data_concurso: Optional[str]
    nivel: str
    horas_por_dia: float
    materias: List[MateriaStatus]


@router.get("/materias-base")
def listar_materias_base():
    """
    Retorna as matérias base para Área Fiscal (estrutura do Estratégia Concursos).
    Futuramente virá do banco de dados.
    """
    return {
        "area": "fiscal",
        "materias": [
            {"nome": "Português", "peso_medio": 10},
            {"nome": "Raciocínio Lógico", "peso_medio": 10},
            {"nome": "Direito Constitucional", "peso_medio": 10},
            {"nome": "Direito Administrativo", "peso_medio": 10},
            {"nome": "Direito Tributário", "peso_medio": 15},
            {"nome": "Contabilidade Geral", "peso_medio": 15},
            {"nome": "Contabilidade Pública", "peso_medio": 10},
            {"nome": "Administração Financeira e Orçamentária", "peso_medio": 10},
            {"nome": "Legislação Tributária", "peso_medio": 10},
            {"nome": "Tecnologia da Informação", "peso_medio": 5},
        ]
    }
