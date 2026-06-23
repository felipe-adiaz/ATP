from fastapi import APIRouter, HTTPException, Header, Query
from fastapi.responses import RedirectResponse
from datetime import datetime, timezone
from app.services.drive_auth_service import gerar_url_autorizacao, trocar_code_por_tokens
from app.services.supabase_client_service import get_supabase_client_for_user, extrair_user_id
from app.services.drive_service import listar_pdfs_da_pasta_studyflow, baixar_pdf
from app.services.pdf_service import processar_pdf_bytes

router = APIRouter()


@router.get("/auth")
async def iniciar_autorizacao(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token ausente ou mal formatado.")
    user_jwt = authorization.replace("Bearer ", "", 1)
    url = gerar_url_autorizacao(state=user_jwt)
    return {"auth_url": url}


@router.get("/callback")
async def callback_google(code: str = Query(...), state: str = Query(...)):
    user_jwt = state
    try:
        tokens = trocar_code_por_tokens(code)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao trocar código por tokens: {str(e)}")
    if not tokens["refresh_token"]:
        raise HTTPException(
            status_code=400,
            detail="Google não retornou refresh_token. Revogue o acesso em myaccount.google.com/permissions e tente novamente.",
        )
    client = get_supabase_client_for_user(user_jwt)
    try:
        user_id = extrair_user_id(user_jwt, client)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    client.table("drive_connections").upsert({
        "user_id": user_id,
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "token_expiry": tokens["expiry"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }, on_conflict="user_id").execute()
    return RedirectResponse(url="https://preview--auditprep.lovable.app/app/files?drive=conectado")


@router.get("/listar-pasta")
async def listar_pasta(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token ausente ou mal formatado.")
    user_jwt = authorization.replace("Bearer ", "", 1)

    client = get_supabase_client_for_user(user_jwt)
    try:
        user_id = extrair_user_id(user_jwt, client)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    resultado_conexao = client.table("drive_connections").select("access_token, refresh_token").eq("user_id", user_id).execute()
    if not resultado_conexao.data:
        raise HTTPException(status_code=404, detail="Usuário ainda não conectou o Google Drive.")

    access_token = resultado_conexao.data[0]["access_token"]
    refresh_token = resultado_conexao.data[0]["refresh_token"]

    try:
        resultado = listar_pdfs_da_pasta_studyflow(access_token, refresh_token)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Erro ao listar arquivos no Drive: {str(e)}")

    novo_access_token = resultado.pop("access_token_atualizado", None)
    if novo_access_token and novo_access_token != access_token:
        client.table("drive_connections").update({
            "access_token": novo_access_token,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("user_id", user_id).execute()

    if not resultado["encontrou_pasta_raiz"]:
        raise HTTPException(
            status_code=404,
            detail="Pasta 'StudyFlow' não encontrada na raiz do Google Drive do usuário.",
        )

    return resultado


@router.post("/processar-pasta")
async def processar_pasta(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token ausente ou mal formatado.")
    user_jwt = authorization.replace("Bearer ", "", 1)

    client = get_supabase_client_for_user(user_jwt)
    try:
        user_id = extrair_user_id(user_jwt, client)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    resultado_conexao = client.table("drive_connections").select("access_token, refresh_token").eq("user_id", user_id).execute()
    if not resultado_conexao.data:
        raise HTTPException(status_code=404, detail="Usuário ainda não conectou o Google Drive.")

    access_token = resultado_conexao.data[0]["access_token"]
    refresh_token = resultado_conexao.data[0]["refresh_token"]

    try:
        listagem = listar_pdfs_da_pasta_studyflow(access_token, refresh_token)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Erro ao listar arquivos no Drive: {str(e)}")

    novo_access_token = listagem.get("access_token_atualizado")
    if novo_access_token and novo_access_token != access_token:
        client.table("drive_connections").update({
            "access_token": novo_access_token,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("user_id", user_id).execute()
        access_token = novo_access_token

    if not listagem["encontrou_pasta_raiz"]:
        raise HTTPException(
            status_code=404,
            detail="Pasta 'StudyFlow' não encontrada na raiz do Google Drive do usuário.",
        )

    ja_processados_resultado = client.table("pdf_processados").select(
        "drive_file_id, drive_modified_time"
    ).eq("user_id", user_id).eq("origem", "google_drive").execute()

    mapa_ja_processados = {
        row["drive_file_id"]: row["drive_modified_time"]
        for row in ja_processados_resultado.data
    }

    processados = []
    pulados = []
    erros = []

    for pdf_info in listagem["pdfs"]:
        drive_file_id = pdf_info["drive_file_id"]
        modified_time_atual = pdf_info["modified_time"]
        modified_time_salvo = mapa_ja_processados.get(drive_file_id)

        if modified_time_salvo == modified_time_atual:
            pulados.append(pdf_info["nome_arquivo"])
            continue

        try:
            pdf_bytes = baixar_pdf(access_token, refresh_token, drive_file_id)
            resultado_extracao = processar_pdf_bytes(pdf_bytes, pdf_info["nome_arquivo"])

            client.table("pdf_processados").upsert({
                "user_id": user_id,
                "arquivo": pdf_info["nome_arquivo"],
                "markdown": resultado_extracao["markdown"],
                "texto_questoes": resultado_extracao["texto_questoes"],
                "total_paginas": resultado_extracao["total_paginas"],
                "paginas_conteudo": resultado_extracao["paginas_conteudo"],
                "paginas_questoes": resultado_extracao["paginas_questoes"],
                "total_palavras_conteudo": resultado_extracao["total_palavras_conteudo"],
                "total_destacadas_conteudo": resultado_extracao["total_destacadas_conteudo"],
                "nivel_dominio": resultado_extracao["nivel_dominio"],
                "origem": "google_drive",
                "drive_file_id": drive_file_id,
                "drive_file_name": pdf_info["nome_arquivo"],
                "drive_modified_time": modified_time_atual,
            }, on_conflict="drive_file_id").execute()

            processados.append(pdf_info["nome_arquivo"])
        except Exception as e:
            erros.append({"arquivo": pdf_info["nome_arquivo"], "erro": str(e)})

    return {
        "total_encontrados": listagem["total_pdfs"],
        "processados": processados,
        "pulados_ja_atualizados": pulados,
        "erros": erros,
    }
