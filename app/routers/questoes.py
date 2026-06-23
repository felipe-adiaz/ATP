from fastapi import APIRouter, HTTPException, Header
from app.services.supabase_client_service import get_supabase_client_for_user, extrair_user_id
from app.services.questoes_service import processar_extracao

router = APIRouter()


@router.post("/extrair")
async def extrair_questoes(pdf_processado_id: str, authorization: str = Header(...)):
    """
    Extrai as questões da seção 'Questões Comentadas' de uma aula já processada,
    usando o parser determinístico (sem IA). Usa cache por hash de conteúdo.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token ausente ou mal formatado.")
    user_jwt = authorization.replace("Bearer ", "", 1)
    client = get_supabase_client_for_user(user_jwt)
    try:
        user_id = extrair_user_id(user_jwt, client)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    resultado_pdf = client.table("pdf_processados").select(
        "id, texto_questoes, user_id, extracao_id"
    ).eq("id", pdf_processado_id).execute()

    if not resultado_pdf.data:
        raise HTTPException(status_code=404, detail="pdf_processado_id não encontrado.")

    registro_pdf = resultado_pdf.data[0]

    if registro_pdf["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Este PDF não pertence ao usuário autenticado.")

    texto_questoes = registro_pdf.get("texto_questoes")
    if not texto_questoes or not texto_questoes.strip():
        raise HTTPException(status_code=400, detail="PDF ainda não teve as questões extraídas. Reprocesse via /drive/processar-pasta.")

    resultado = processar_extracao(texto_questoes)
    hash_conteudo = resultado["conteudo_hash"]

    extracao_existente = client.table("extracoes_questoes").select("id").eq(
        "conteudo_hash", hash_conteudo
    ).execute()

    if extracao_existente.data:
        extracao_id = extracao_existente.data[0]["id"]
        reaproveitado = True
    else:
        nova_extracao = client.table("extracoes_questoes").insert({
            "conteudo_hash": hash_conteudo,
            "status": resultado["status"],
            "total_questoes": resultado["total_questoes"],
            "total_esperado": resultado["total_esperado"],
            "texto_origem": resultado["texto_origem"],
            "resposta_bruta_ia": resultado["resposta_bruta_ia"],
            "lotes_entrada_debug": resultado["lotes_entrada_debug"],
        }).execute()
        extracao_id = nova_extracao.data[0]["id"]
        reaproveitado = False

        if resultado["questoes"]:
            linhas_questoes = [
                {
                    "extracao_id": extracao_id,
                    "user_id": user_id,
                    "numero_questao": q.get("numero_questao"),
                    "banca": q.get("banca"),
                    "orgao": q.get("orgao"),
                    "cargo": q.get("cargo"),
                    "ano": q.get("ano"),
                    "enunciado": q.get("enunciado") or "",
                    "alternativa_a": q.get("alternativa_a"),
                    "alternativa_b": q.get("alternativa_b"),
                    "alternativa_c": q.get("alternativa_c"),
                    "alternativa_d": q.get("alternativa_d"),
                    "alternativa_e": q.get("alternativa_e"),
                    "gabarito": q.get("gabarito"),
                    "comentario": q.get("comentario"),
                    "tipo_gabarito": q.get("tipo_gabarito"),
                    "id_unico_questao": q.get("id_unico_questao"),
                    "revisar": bool(q.get("revisar")),
                    "motivo_revisao": q.get("motivo_revisao"),
                    "origem": "pdf_consumo",
                }
                for q in resultado["questoes"]
            ]
            client.table("questoes_banco").upsert(
                linhas_questoes, on_conflict="extracao_id,numero_questao"
            ).execute()

    client.table("pdf_processados").update({
        "extracao_id": extracao_id
    }).eq("id", pdf_processado_id).execute()

    return {
        "extracao_id": extracao_id,
        "reaproveitado": reaproveitado,
        "status": resultado["status"],
        "total_questoes": resultado["total_questoes"],
        "total_esperado": resultado["total_esperado"],
    }
