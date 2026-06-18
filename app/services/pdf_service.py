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


def eh_secao_questoes(texto_pagina: str) -> bool:
    """
    Verifica se a página é uma seção de questões/gabarito.
    Compara com as primeiras linhas não-vazias da página.
    """
    linhas = [l.strip() for l in texto_pagina.split('\n') if l.strip()]
    # Verifica nas primeiras 3 linhas não-vazias
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
    texto_final = re.sub(r'\n{3,}', '\n\n', texto_final)
    return texto_final.strip()


def processar_pdf_bytes(pdf_bytes: bytes, nome_arquivo: str) -> dict:
    """
    Processa um PDF em memória (bytes) e retorna:
    - markdown: texto das páginas de conteúdo com marcações
    - nivel_dominio: % de palavras destacadas APENAS nas páginas de conteúdo
    
    Identifica automaticamente seções de questões (QUESTÕES COMENTADAS,
    LISTA DE QUESTÕES, GABARITO) e as exclui do cálculo de domínio,
    mesmo que o PDF alterne entre conteúdo e questões várias vezes.
    Ignora as primeiras 6 páginas na detecção (índice/capa).
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

        # A partir da página 7, detectar transições de seção
        if num >= 6:
            if eh_secao_questoes(texto_pagina):
                em_secao_questoes = True
            else:
                # Voltou para conteúdo se a página tem texto substancial
                # e não é só gabarito/número de questão
                if palavras_pagina > 20:
                    em_secao_questoes = False

        entrada = {
            "numero": num + 1,
            "texto": texto_md,
            "palavras": palavras_pagina,
            "destacadas": destacadas_pagina,
            "tipo": "questoes" if em_secao_questoes else "conteudo",
        }

        if em_secao_questoes:
            if texto_md.strip():
                paginas_questoes.append(entrada)
        else:
            total_palavras_conteudo += palavras_pagina
            total_destacadas_conteudo += destacadas_pagina
            if texto_md.strip():
                paginas_conteudo.append(entrada)

    # Nível de domínio calculado SOMENTE sobre páginas de conteúdo
    nivel_dominio = round(
        (total_destacadas_conteudo / total_palavras_conteudo * 100), 1
    ) if total_palavras_conteudo > 0 else 0.0

    # Markdown só das páginas de conteúdo
    markdown = f"# {nome_arquivo}\n\n"
    for p in paginas_conteudo:
        markdown += f"\n\n---\n## Página {p['numero']}\n\n{p['texto']}"

    return {
        "markdown": markdown,
        "total_paginas": len(doc),
        "paginas_conteudo": len(paginas_conteudo),
        "paginas_questoes": len(paginas_questoes),
        "total_palavras_conteudo": total_palavras_conteudo,
        "total_destacadas_conteudo": total_destacadas_conteudo,
        "nivel_dominio": nivel_dominio,
        "paginas": paginas_conteudo,
    }


def calcular_status_materia(nivel_dominio: float, tem_pdf: bool) -> str:
    """
    Determina o status de uma matéria com base no nível de domínio.
    - sem_pdf: aluno ainda não subiu material
    - consumo: tem PDF mas ainda estudando (< 30% destacado)
    - revisao_parcial: em progresso (30-70%)
    - revisao: domínio consolidado (> 70%)
    """
    if not tem_pdf:
        return "sem_pdf"
    if nivel_dominio < 30:
        return "consumo"
    elif nivel_dominio < 70:
        return "revisao_parcial"
    else:
        return "revisao"
