# -*- coding: utf-8 -*-
"""
Serviço de extração de highlights de PDFs.
Baseado no script original do Felipe Diaz.
"""
import re
import fitz  # PyMuPDF

# Títulos que indicam início de seção de questões (ignorar no cálculo de domínio)
PADROES_SECAO_QUESTOES = [
    r"^QUEST",
    r"^LISTA\s+DE\s+QUEST",
    r"^GABARITO",
    r"^EXERC",
]

PADROES_MARCA_DAGUA = [
    r"\d{11}\s*-\s*[A-ZÀ-Úa-zà-ú][A-ZÀ-Úa-zà-ú ]*",
    r"www\.estrategiaconcursos\.com\.br",
]


def limpar_marca_dagua(texto: str) -> str:
    for padrao in PADROES_MARCA_DAGUA:
        texto = re.sub(padrao, "", texto)
    texto = re.sub(r'\n{3,}', '\n\n', texto)
    texto = re.sub(r'[ \t]{2,}', ' ', texto)
    return texto.strip()


def detectar_linhas_repetidas(textos_por_pagina: list, limiar: float = 0.6, tamanho_minimo: int = 5) -> set:
    from collections import Counter

    contagem = Counter()
    for texto in textos_por_pagina:
        linhas_unicas_da_pagina = {
            l.strip() for l in texto.split("\n")
            if len(l.strip()) >= tamanho_minimo
        }
        for linha in linhas_unicas_da_pagina:
            contagem[linha] += 1

    total_paginas = len(textos_por_pagina) or 1
    return {linha for linha, qtd in contagem.items() if qtd / total_paginas >= limiar}


def remover_linhas_repetidas(texto: str, linhas_repetidas: set) -> str:
    linhas_filtradas = [l for l in texto.split("\n") if l.strip() not in linhas_repetidas]
    resultado = "\n".join(linhas_filtradas)
    resultado = re.sub(r'\n{3,}', '\n\n', resultado)
    return resultado.strip()


def eh_secao_questoes(texto_pagina: str) -> bool:
    linhas = [l.strip() for l in texto_pagina.split('\n') if l.strip()]
    for linha in linhas[:3]:
        linha_upper = linha.upper()
        for padrao in PADROES_SECAO_QUESTOES:
            if re.match(padrao, linha_upper):
                return True
    return False


def get_highlight_rects(page):
    rects = []
    for annot in page.annots():
        if annot.type[0] == 8:
            vertices = annot.vertices
            if vertices:
                for i in range(0, len(vertices), 4):
                    quad = vertices[i:i+4]
                    if len(quad) == 4:
                        xs = [p[0] for p in quad]
                        ys = [p[1] for p in quad]
                        rects.append(fitz.Rect(min(xs), min(ys), max(xs), max(ys)))
            else:
                rects.append(annot.rect)
    return rects


def contar_sobreposicoes(x, y, highlight_rects, margem=2):
    count = 0
    for rect in highlight_rects:
        if (rect.x0 - margem <= x <= rect.x1 + margem and
                rect.y0 - margem <= y <= rect.y1 + margem):
            count += 1
    return count


def formatar_destaque(texto, nivel):
    t = texto.strip()
    if not t:
        return texto
    if nivel == 0:
        return texto + " "
    elif nivel == 1:
        return "==" + t + "== "
    elif nivel == 2:
        return "**==" + t + "==** "
    else:
        return "***==" + t + "==*** "


def extrair_pagina(page, highlight_rects):
    words = page.get_text("words")
    if not words:
        return ""

    resultado = []
    buffer_palavras = []
    nivel_atual = 0
    ultimo_bloco = None
    ultima_linha = None

    def flush_buffer():
        if buffer_palavras:
            texto = " ".join(buffer_palavras)
            resultado.append(formatar_destaque(texto, nivel_atual))
            buffer_palavras.clear()

    for word_info in words:
        x0, y0, x1, y1, word, block_no, line_no, word_idx = word_info
        if ultimo_bloco is not None and block_no != ultimo_bloco:
            flush_buffer()
            resultado.append("\n\n")
        elif ultima_linha is not None and line_no != ultima_linha:
            flush_buffer()
            resultado.append("\n")
        cx = (x0 + x1) / 2
        cy = (y0 + y1) / 2
        nivel = min(contar_sobreposicoes(cx, cy, highlight_rects), 3)
        if nivel != nivel_atual:
            flush_buffer()
            nivel_atual = nivel
        buffer_palavras.append(word)
        ultimo_bloco = block_no
        ultima_linha = line_no

    flush_buffer()
    texto_final = "".join(resultado)
    texto_final = limpar_marca_dagua(texto_final)
    return texto_final


def processar_pdf_bytes(pdf_bytes: bytes, nome_arquivo: str) -> dict:
    """
    Processa um PDF em memória (bytes) e retorna:
    - markdown: texto das páginas de conteúdo com marcações
    - nivel_dominio: % de palavras destacadas APENAS nas páginas de conteúdo
    - texto_questoes: texto bruto das páginas de questões, paginado com
      marcadores '----- PAGINA N -----', pronto para o parser determinístico

    Regra de seção: nos PDFs do Estratégia, a seção de QUESTÕES COMENTADAS /
    LISTA DE QUESTÕES / GABARITO fica no FIM da aula e não volta mais para
    conteúdo. Por isso, uma vez detectada essa seção, todas as páginas
    seguintes são tratadas como questões (não há retorno para conteúdo).
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    paginas_conteudo = []
    paginas_questoes = []
    total_palavras_conteudo = 0
    total_destacadas_conteudo = 0

    em_secao_questoes = False

    for num in range(len(doc)):
        page = doc[num]
        texto_pagina = page.get_text("text").strip()
        highlight_rects = get_highlight_rects(page)
        texto_md = extrair_pagina(page, highlight_rects)

        words = page.get_text("words")
        palavras_pagina = len(words)
        destacadas_pagina = sum(
            1 for w in words
            if contar_sobreposicoes((w[0]+w[2])/2, (w[1]+w[3])/2, highlight_rects) > 0
        )

        # A partir da página 7, ao detectar o início da seção de questões,
        # entra na seção e NÃO volta mais para conteúdo (a seção de questões/
        # lista/gabarito vai até o fim da aula).
        if num >= 6 and not em_secao_questoes and eh_secao_questoes(texto_pagina):
            em_secao_questoes = True

        entrada = {
            "numero": num + 1,
            "texto": texto_md,
            "palavras": palavras_pagina,
            "destacadas": destacadas_pagina,
            "tipo": "questoes" if em_secao_questoes else "conteudo",
        }

        if em_secao_questoes:
            # Guarda o texto bruto para o parser determinístico, mesmo que a
            # página não tenha texto "markdown" (ex.: páginas só de gabarito).
            if texto_pagina.strip():
                entrada["texto_raw"] = texto_pagina
                paginas_questoes.append(entrada)
        else:
            total_palavras_conteudo += palavras_pagina
            total_destacadas_conteudo += destacadas_pagina
            if texto_md.strip():
                paginas_conteudo.append(entrada)

    linhas_repetidas = detectar_linhas_repetidas([p["texto"] for p in paginas_conteudo])
    for p in paginas_conteudo:
        p["texto"] = remover_linhas_repetidas(p["texto"], linhas_repetidas)

    nivel_dominio = round(
        (total_destacadas_conteudo / total_palavras_conteudo * 100), 1
    ) if total_palavras_conteudo > 0 else 0.0

    markdown = f"# {nome_arquivo}\n\n"
    for p in paginas_conteudo:
        markdown += f"\n\n---\n## Página {p['numero']}\n\n{p['texto']}"

    # Monta texto_questoes com marcadores de página para o parser determinístico
    texto_questoes = ""
    for p in paginas_questoes:
        texto_questoes += f"\n----- PAGINA {p['numero']} -----\n{p.get('texto_raw', '')}"

    return {
        "markdown": markdown,
        "total_paginas": len(doc),
        "paginas_conteudo": len(paginas_conteudo),
        "paginas_questoes": len(paginas_questoes),
        "total_palavras_conteudo": total_palavras_conteudo,
        "total_destacadas_conteudo": total_destacadas_conteudo,
        "nivel_dominio": nivel_dominio,
        "paginas": paginas_conteudo,
        "texto_questoes": texto_questoes,
    }


def calcular_status_materia(nivel_dominio: float, tem_pdf: bool) -> str:
    if not tem_pdf:
        return "sem_pdf"
    if nivel_dominio < 30:
        return "consumo"
    elif nivel_dominio < 70:
        return "revisao_parcial"
    else:
        return "revisao"
