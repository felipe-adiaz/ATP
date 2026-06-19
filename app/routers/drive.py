from fastapi import APIRouter, HTTPException, Header, Query
from fastapi.responses import RedirectResponse
from datetime import datetime, timezone

from app.services.drive_auth_service import gerar_url_autorizacao, trocar_code_por_tokens
from app.services.supabase_client_service import get_supabase_client_for_user, extrair_user_id

router = APIRouter()


@router.get("/auth")
async def iniciar_autorizacao(authorization: str = Header(...)):
    """
    Recebe o JWT do usuário logado (header Authorization: Bearer <token>)
    e devolve a URL do Google para onde o frontend deve redirecionar o usuário.
    O próprio JWT vira o 'state', para sabermos de quem é o callback depois.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token ausente ou mal formatado.")
    user_jwt = authorization.replace("Bearer ", "", 1)

    url = gerar_url_autorizacao(state=user_jwt)
    return {"auth_url": url}


@router.get("/callback")
async def callback_google(code: str = Query(...), state: str = Query(...)):
    """
    O Google redireciona para cá depois que o usuário autoriza o acesso.
    'state' contém o JWT que mandamos lá no /auth, então sabemos
    para qual usuário salvar os tokens.
    """
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

    # Ajuste esta URL para a tela real do frontend que deve abrir após conectar
    return RedirectResponse(url="https://preview--auditprep.lovable.app/app/files?drive=conectado")
