from fastapi import APIRouter, HTTPException, Header
from app.services.supabase_client_service import get_supabase_client_for_user, extrair_user_id
from app.services.questoes_service import processar_extracao

router = APIRouter()


@router.post("/extrair")
async def extrair_questoes(pdf_processado_id: str, authorization: str = Header(...)):
    """
    Extrai as questões da seção 'Questões Comentadas' de uma aula já processada.
    Usa cache por hash de conteúdo: se outro aluno (ou reprocessamento) já gerou
    uma extração idêntica, reaproveita em vez de chamar a IA de novo.
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
        "id, markdown, user_id, extracao_id"
    ).eq("id", pdf_processado_id).execute()

    if not resultado_pdf.data:
        raise HTTPException(status_code=404, detail="pdf_processado_id não encontrado.")

    registro_pdf = resultado_pdf.data[0]

    if registro_pdf["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Este PDF não pertence ao usuário autenticado.")

    markdown = registro_pdf["markdown"]
    if not markdown:
        raise HTTPException(status_code=400, detail="Este PDF ainda não tem markdown processado.")

    resultado = processar_extracao(markdown)
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
        }).execute()
        extracao_id = nova_extracao.data[0]["id"]
        reaproveitado = False

        if resultado["questoes"]:
            linhas_questoes = [
                {
                    "extracao_id": extracao_id,
                    "numero_questao": q.get("numero_questao"),
                    "banca": q.get("banca"),
                    "orgao": q.get("orgao"),
                    "ano": q.get("ano"),
                    "enunciado": q.get("enunciado"),
                    "alternativa_a": q.get("alternativa_a"),
                    "alternativa_b": q.get("alternativa_b"),
                    "alternativa_c": q.get("alternativa_c"),
                    "alternativa_d": q.get("alternativa_d"),
                    "alternativa_e": q.get("alternativa_e"),
                    "gabarito": q.get("gabarito"),
                    "comentario": q.get("comentario"),
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
