# -*- coding: utf-8 -*-
"""
Localização PRECISA de seções de "Questões Comentadas" em PDFs de aula
(Estratégia Concursos).
"""
import re


PREFIXO_COMENTADAS = "QUESTÕES COMENTADAS"
PREFIXO_LISTA = "LISTA DE QUESTÕES"
PALAVRA_GABARITO = "GABARITO"

PADRAO_BANCA_COMENTADAS = re.compile(
    r'^[0-9A-ZÀ-Ú./ ]{1,30}[–-]\s*QUESTÕES COMENTADAS\b'
)

PADRAO_NUMERACAO_CAPITULO = re.compile(r'^\d{1,3}\s*[-.):>=]*\s*')
PADRAO_PONTOS_PREENCHIMENTO = re.compile(r'\.{4,}')

PAGINA_LIMITE_SUMARIO = 5


def linha_parece_entrada_de_sumario(linha_original: str) -> bool:
    return bool(PADRAO_PONTOS_PREENCHIMENTO.search(linha_original))


def normalizar_linha(linha: str) -> str:
    linha = linha.strip().upper()
    linha = PADRAO_NUMERACAO_CAPITULO.sub('', linha)
    return linha


def _sem_espacos(texto: str) -> str:
    return texto.replace(" ", "")


def linha_bate_prefixo(linha_norm: str, prefixo: str) -> bool:
    if linha_norm.startswith(prefixo):
        return True
    return _sem_espacos(linha_norm).startswith(_sem_espacos(prefixo))


def linha_eh_exatamente(linha_norm: str, palavra: str) -> bool:
    if linha_norm == palavra:
        return True
    return _sem_espacos(linha_norm) == _sem_espacos(palavra)


def detectar_tipo_heading(linha_norm: str):
    if linha_bate_prefixo(linha_norm, PREFIXO_COMENTADAS):
        return "principal"
    if PADRAO_BANCA_COMENTADAS.match(linha_norm):
        return "banca"
    if linha_bate_prefixo(linha_norm, PREFIXO_LISTA):
        return "lista"
    if linha_eh_exatamente(linha_norm, PALAVRA_GABARITO):
        return "gabarito"
    return None


def extrair_linhas_com_pagina(doc):
    linhas = []
    paginas_por_linha = []
    for num_pagina, pagina in enumerate(doc, start=1):
        texto_pagina = pagina.get_text("text")
        for linha in texto_pagina.split("\n"):
            linhas.append(linha)
            paginas_por_linha.append(num_pagina)
    return linhas, paginas_por_linha


def localizar_ocorrencias(linhas, paginas_por_linha):
    ocorrencias = []
    for idx, linha in enumerate(linhas):
        linha_norm = normalizar_linha(linha)
        if not linha_norm:
            continue
        tipo = detectar_tipo_heading(linha_norm)
        if not tipo:
            continue

        pagina = paginas_por_linha[idx]
        if linha_parece_entrada_de_sumario(linha):
            continue
        if pagina <= PAGINA_LIMITE_SUMARIO:
            continue

        ocorrencias.append({
            "tipo": tipo,
            "linha_indice": idx,
            "linha_texto": linha.strip(),
            "pagina": pagina,
        })
    return ocorrencias


def _fechar(bloco, fim, linhas):
    inicio = bloco["inicio_linha"]
    bloco["fim_linha"] = fim
    bloco["texto"] = "\n".join(linhas[inicio:fim]).strip()
    return bloco


def montar_blocos_comentados(ocorrencias, linhas):
    total = len(linhas)
    blocos = []
    aberto = None

    def abrir(idx, heading_texto):
        return {
            "origem": "questoes_comentadas",
            "inicio_linha": idx,
            "heading": heading_texto,
        }

    for oc in sorted(ocorrencias, key=lambda o: o["linha_indice"]):
        tipo = oc["tipo"]
        idx = oc["linha_indice"]

        if tipo == "principal":
            if aberto is not None:
                blocos.append(_fechar(aberto, idx, linhas))
            aberto = abrir(idx, oc["linha_texto"])

        elif tipo == "banca":
            if aberto is None:
                aberto = abrir(idx, oc["linha_texto"])

        elif tipo == "lista":
            if aberto is not None:
                blocos.append(_fechar(aberto, idx, linhas))
                aberto = None

        elif tipo == "gabarito":
            if aberto is not None:
                blocos.append(_fechar(aberto, idx, linhas))
                aberto = None

    if aberto is not None:
        blocos.append(_fechar(aberto, total, linhas))

    return blocos


def montar_blocos_fallback(ocorrencias, linhas):
    total = len(linhas)
    blocos = []
    ocs = sorted(ocorrencias, key=lambda o: o["linha_indice"])

    for i, oc in enumerate(ocs):
        if oc["tipo"] != "lista":
            continue
        inicio = oc["linha_indice"]
        fim_lista = total
        gab_ini = None
        gab_fim = total
        for prox in ocs[i + 1:]:
            if prox["tipo"] == "lista":
                fim_lista = prox["linha_indice"]
                break
            if prox["tipo"] == "gabarito" and gab_ini is None:
                gab_ini = prox["linha_indice"]
                fim_lista = gab_ini
                continue
            if gab_ini is not None:
                gab_fim = prox["linha_indice"]
                break

        texto_lista = "\n".join(linhas[inicio:fim_lista]).strip()
        texto_gab = ""
        if gab_ini is not None:
            texto_gab = "\n".join(linhas[gab_ini:gab_fim]).strip()

        blocos.append({
            "origem": "lista_e_gabarito",
            "texto": texto_lista,
            "texto_gabarito": texto_gab,
            "inicio_linha": inicio,
            "fim_linha": fim_lista,
        })

    blocos.sort(key=lambda b: b["inicio_linha"])
    return blocos


def montar_blocos(ocorrencias, linhas):
    tem_comentadas = any(
        o["tipo"] in ("principal", "banca") for o in ocorrencias
    )
    if tem_comentadas:
        blocos = montar_blocos_comentados(ocorrencias, linhas)
    else:
        blocos = montar_blocos_fallback(ocorrencias, linhas)
    blocos.sort(key=lambda b: b["inicio_linha"])
    return blocos


def localizar_secoes_questoes(doc):
    linhas, paginas = extrair_linhas_com_pagina(doc)
    ocorrencias = localizar_ocorrencias(linhas, paginas)
    blocos = montar_blocos(ocorrencias, linhas)
    return blocos, ocorrencias
