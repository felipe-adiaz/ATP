"""
Service responsável por listar arquivos no Google Drive do usuário.
Usa o access_token salvo em drive_connections (via drive_auth_service).
Não baixa conteúdo de arquivo nenhum aqui — só lista metadados.
"""

import os
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleAuthRequest

NOME_PASTA_RAIZ = "StudyFlow"

GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"


def _montar_credenciais(access_token: str, refresh_token: str) -> Credentials:
    """
    Monta as credenciais completas, com tudo que a lib do Google precisa
    para renovar o access_token sozinha caso ele já tenha expirado.
    """
    return Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri=GOOGLE_TOKEN_URI,
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
    )


def _montar_client_drive(access_token: str, refresh_token: str):
    """
    Cria o client autenticado da Drive API. Se o access_token estiver
    expirado, renova automaticamente usando o refresh_token antes de
    montar o client.
    """
    credenciais = _montar_credenciais(access_token, refresh_token)

    if credenciais.expired or not credenciais.valid:
        credenciais.refresh(GoogleAuthRequest())

    client = build("drive", "v3", credentials=credenciais)
    return client, credenciais.token


def _buscar_id_pasta_raiz(client_drive):
    """Encontra o ID da pasta StudyFlow na raiz do Drive do usuário. Retorna None se não existir."""
    query = (
        f"name = '{NOME_PASTA_RAIZ}' "
        "and mimeType = 'application/vnd.google-apps.folder' "
        "and trashed = false"
    )
    resultado = client_drive.files().list(
        q=query,
        fields="files(id, name)",
        pageSize=1,
    ).execute()

    pastas = resultado.get("files", [])
    if not pastas:
        return None
    return pastas[0]["id"]


def _listar_conteudo_pasta(client_drive, pasta_id: str):
    """Lista o conteúdo direto (não recursivo) de uma pasta pelo ID."""
    itens = []
    page_token = None

    while True:
        resultado = client_drive.files().list(
            q=f"'{pasta_id}' in parents and trashed = false",
            fields="nextPageToken, files(id, name, mimeType, modifiedTime)",
            pageToken=page_token,
            pageSize=100,
        ).execute()

        itens.extend(resultado.get("files", []))
        page_token = resultado.get("nextPageToken")
        if not page_token:
            break

    return itens


def _percorrer_recursivo(client_drive, pasta_id: str, caminho_atual: str, nome_subpasta_imediata: str, lista_pdfs: list):
    """Percorre uma pasta recursivamente, acumulando PDFs encontrados em lista_pdfs."""
    itens = _listar_conteudo_pasta(client_drive, pasta_id)

    for item in itens:
        eh_pasta = item["mimeType"] == "application/vnd.google-apps.folder"
        caminho_item = f"{caminho_atual}/{item['name']}"

        if eh_pasta:
            _percorrer_recursivo(
                client_drive,
                item["id"],
                caminho_item,
                item["name"],  # essa pasta passa a ser a "subpasta imediata" para os filhos dela
                lista_pdfs,
            )
        elif item["mimeType"] == "application/pdf":
            lista_pdfs.append({
                "drive_file_id": item["id"],
                "nome_arquivo": item["name"],
                "caminho_completo": caminho_item,
                "subpasta_imediata": nome_subpasta_imediata,
                "modified_time": item["modifiedTime"],
            })


def listar_pdfs_da_pasta_studyflow(access_token: str, refresh_token: str) -> dict:
    """
    Função principal do service. Localiza a pasta StudyFlow na raiz do Drive
    do usuário e retorna todos os PDFs encontrados nela (recursivo).

    Se o access_token estiver expirado, é renovado automaticamente; o token
    (possivelmente novo) volta no campo "access_token_atualizado", para que
    quem chamou possa salvar de volta no banco.
    """
    client_drive, access_token_atualizado = _montar_client_drive(access_token, refresh_token)

    pasta_raiz_id = _buscar_id_pasta_raiz(client_drive)
    if pasta_raiz_id is None:
        return {
            "encontrou_pasta_raiz": False,
            "total_pdfs": 0,
            "pdfs": [],
            "access_token_atualizado": access_token_atualizado,
        }

    lista_pdfs = []
    _percorrer_recursivo(
        client_drive,
        pasta_raiz_id,
        caminho_atual=NOME_PASTA_RAIZ,
        nome_subpasta_imediata=None,
        lista_pdfs=lista_pdfs,
    )

    return {
        "encontrou_pasta_raiz": True,
        "total_pdfs": len(lista_pdfs),
        "pdfs": lista_pdfs,
        "access_token_atualizado": access_token_atualizado,
    }
