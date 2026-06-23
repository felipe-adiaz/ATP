# -*- coding: utf-8 -*-
"""
Limpeza de rodapé / marca d'água para o texto de questões.
Reaproveita a mesma lógica do serviço de highlights (descrita no briefing):
- remove a marca d'água "CPF + nome" e a URL do Estratégia;
- detecta e remove linhas que se repetem na maioria das páginas
  (nome de professores, "Aula NN", título do curso etc.), comparando o
  próprio documento consigo mesmo, sem lista fixa.
No fluxo final, a limpeza pesada acontece na FUNÇÃO DE IMPORTAÇÃO. Este
módulo está aqui para o serviço de questões também conseguir limpar os
campos (enunciado/comentário) antes de gravar, já que ele lê o texto cru
das páginas de questões.
"""
import re
from collections import Counter

# "01000099130 - Luis Felipe Alves Diaz" -> marca d'água por usuário.
PADRAO_MARCA_CPF_NOME = re.compile(r'^\s*\d{11}\s*-\s*\S.*$')
PADRAO_URL_ESTRATEGIA = re.compile(r'www\.estrategiaconcursos\.com\.br', re.IGNORECASE)

# Caracteres invisíveis de largura zero que quebram o parser.
PADRAO_ZERO_WIDTH = re.compile(r'[\u200b\u200c\u200d\ufeff]')


def limpar_marca_dagua(texto: str) -> str:
    """Remove caracteres invisíveis, linhas de marca d'água (CPF+nome) e a URL do Estratégia."""
    # Remove zero-width space/non-joiner/joiner e BOM antes de qualquer outra coisa.
    texto = PADRAO_ZERO_WIDTH.sub('', texto)

    saida = []
    for linha in texto.split("\n"):
        if PADRAO_MARCA_CPF_NOME.match(linha):
            continue
        if PADRAO_URL_ESTRATEGIA.search(linha):
            continue
        saida.append(linha)
    return "\n".join(saida)


def detectar_linhas_repetidas(textos_por_pagina, limiar=0.6, tamanho_minimo=5):
    """
    Detecta linhas que aparecem em >= `limiar` das páginas (cabeçalho/rodapé
    repetido: nome de professor, "Aula 05", título do curso). Compara o
    documento consigo mesmo; nada é fixo no código.
    """
    n_pag = len(textos_por_pagina)
    if n_pag == 0:
        return set()
    contagem = Counter()
    for texto in textos_por_pagina:
        vistas = {l.strip() for l in texto.split("\n") if len(l.strip()) >= tamanho_minimo}
        for s in vistas:
            contagem[s] += 1
    limite = max(2, int(limiar * n_pag))
    return {s for s, c in contagem.items() if c >= limite}


def remover_linhas_repetidas(texto: str, linhas_repetidas) -> str:
    if not linhas_repetidas:
        return texto
    return "\n".join(l for l in texto.split("\n") if l.strip() not in linhas_repetidas)


def limpar_texto_questoes(texto_bloco: str, linhas_repetidas=None) -> str:
    """Pipeline de limpeza aplicado ao texto de UM bloco de questões."""
    t = limpar_marca_dagua(texto_bloco)
    t = remover_linhas_repetidas(t, linhas_repetidas)
    return t
