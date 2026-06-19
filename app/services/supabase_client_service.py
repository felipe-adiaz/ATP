import os
from supabase import create_client, Client


def get_supabase_client_for_user(user_jwt: str) -> Client:
    """
    Cria um client Supabase autenticado como o usuário dono do JWT.
    Todas as operações feitas com esse client respeitam as políticas
    de RLS como se fosse o próprio usuário logado fazendo a chamada.
    """
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_PUBLISHABLE_KEY"]
    client = create_client(url, key)
    client.postgrest.auth(user_jwt)
    return client


def extrair_user_id(user_jwt: str, client: Client) -> str:
    """Pega o user_id (uuid) a partir do JWT, validando via Supabase Auth."""
    user_response = client.auth.get_user(user_jwt)
    if not user_response or not user_response.user:
        raise ValueError("Token inválido ou expirado.")
    return user_response.user.id
