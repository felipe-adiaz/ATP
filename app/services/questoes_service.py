# -*- coding: utf-8 -*-
import hashlib
import re
from app.services.localizar_secoes_v2 import localizar_secoes_questoes_em_texto
from app.services.parser_questoes import parsear_questoes_do_bloco


def calcular_hash(texto: str) -> str:
    return hashlib.sha256((texto or "").encode("utf-8")).hexdigest()


# Caracteres invisíveis de largura zero (zero-width space/non-joiner/joiner e BOM)
# que aparecem colados ao número da questão em alguns PDFs (ex.: "1.\u200b") e
# impedem o parser de detectar o início da questão. Removidos antes de tudo.
_PADRAO_ZERO_WIDTH = re.compile(r"[\u200b\u200c\u200d\ufeff]")

_PADRAO_INICIO = re.compile(r"\d{1,3}\.\s*\([^)]*(?:19|20)\d{2}[^)]*\)")


def processar_extracao(texto_questoes: str) -> dict:
    # Limpa caracteres de largura zero ANTES de hashear, localizar e parsear.
    texto_questoes = _PADRAO_ZERO_WIDTH.sub("", texto_questoes or "")

    h = calcular_hash(texto_questoes or "")
    base = {"conteudo_hash": h, "resposta_bruta_ia": None, "lotes_entrada_debug": None}
    if not texto_questoes or not texto_questoes.strip():
        return {
            **base,
            "status": "sem_secao",
            "total_questoes": 0,
            "total_esperado": 0,
            "texto_origem": None,
            "questoes": [],
        }
    blocos, _ = localizar_secoes_questoes_em_texto(texto_questoes)
    questoes = []
    for b in blocos:
        if b.get("origem") != "questoes_comentadas":
            continue
        questoes.extend(parsear_questoes_do_bloco(b["texto"], "pdf", b["inicio_linha"]))
    for i, q in enumerate(questoes, start=1):
        q["numero_questao"] = i
    total = len(questoes)
    esperado = len(_PADRAO_INICIO.findall(texto_questoes))
    revisar = sum(1 for q in questoes if q.get("revisar"))
    status = "ok" if (revisar == 0 and total == esperado) else "revisar"
    return {
        **base,
        "status": status,
        "total_questoes": total,
        "total_esperado": esperado,
        "texto_origem": texto_questoes[:5000],
        "questoes": questoes,
    }
