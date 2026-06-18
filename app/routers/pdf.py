from fastapi import APIRouter, UploadFile, File, HTTPException
from app.services.pdf_service import processar_pdf_bytes, calcular_status_materia

router = APIRouter()


@router.post("/processar")
async def processar_pdf(file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Somente arquivos PDF são aceitos.")
    pdf_bytes = await file.read()
    if len(pdf_bytes) == 0:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")
    try:
        resultado = processar_pdf_bytes(pdf_bytes, file.filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar PDF: {str(e)}")
    status = calcular_status_materia(resultado["nivel_dominio"], tem_pdf=True)
    return {
        "arquivo": file.filename,
        "status_materia": status,
        "nivel_dominio": resultado["nivel_dominio"],
        "total_paginas": resultado["total_paginas"],
        "paginas_conteudo": resultado["paginas_conteudo"],
        "paginas_questoes": resultado["paginas_questoes"],
        "total_palavras_conteudo": resultado["total_palavras_conteudo"],
        "total_destacadas_conteudo": resultado["total_destacadas_conteudo"],
        "markdown": resultado["markdown"],
        "paginas": resultado["paginas"],
    }


@router.post("/nivel-dominio")
async def calcular_dominio(file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Somente arquivos PDF são aceitos.")
    pdf_bytes = await file.read()
    try:
        resultado = processar_pdf_bytes(pdf_bytes, file.filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro: {str(e)}")
    status = calcular_status_materia(resultado["nivel_dominio"], tem_pdf=True)
    return {
        "arquivo": file.filename,
        "nivel_dominio": resultado["nivel_dominio"],
        "status_materia": status,
        "total_paginas": resultado["total_paginas"],
        "paginas_conteudo": resultado["paginas_conteudo"],
        "paginas_questoes": resultado["paginas_questoes"],
        "total_palavras_conteudo": resultado["total_palavras_conteudo"],
        "total_destacadas_conteudo": resultado["total_destacadas_conteudo"],
    }