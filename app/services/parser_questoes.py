# -*- coding: utf-8 -*-
"""
Parser de questões individuais dentro de blocos "QUESTÕES COMENTADAS"
(Projeto Audit Prep - Estratégia Concursos).

Este módulo é a 2ª etapa do pipeline. A 1ª etapa (localizar_secoes_v2.py,
já validada e intocada) entrega blocos de texto bruto contendo várias
questões comentadas juntas. Este módulo separa esse texto em questões
individuais e extrai seus campos.

Arquitetura modular: cada heurística de detecção é uma função isolada,
para que novas variações encontradas em testes futuros (mais PDFs) possam
ser adicionadas ou ajustadas sem mexer no orquestrador principal.

Princípio geral adotado (decisão do usuário, sessão de retomada):
    Na dúvida, SINALIZAR para revisão manual (revisar=True) — nunca
    decidir nem descartar silenciosamente.
"""
import re


# ---------------------------------------------------------------------------
# Regex base
# ---------------------------------------------------------------------------

# Formato 1: "1. (CESPE – LOREM ÓRGÃO – ANALISTA – 2018)" tudo na mesma linha.
# Exige PONTO após o número (diferencia de nota de rodapé "1 (Autor, 2010)").
PADRAO_INICIO_MESMA_LINHA = re.compile(
    r'^(?P<numero>\d{1,3})\.\s*\((?P<cabecalho>(?:[^()]|\([^()]*\))+)\)'
)

# Formato 2: número sozinho numa linha ("1."), cabeçalho na linha seguinte.
PADRAO_NUMERO_SOZINHO = re.compile(r'^(?P<numero>\d{1,3})\.\s*$')

# Cabeçalho na linha seguinte ao número (Formato 2). Aceita parênteses
# ANINHADOS no cabeçalho, ex.: "(FGV/AF (SEFAZ PR)/SEFAZ PR/2025)".
PADRAO_CABECALHO_LINHA_SEGUINTE = re.compile(
    r'^\((?P<cabecalho>(?:[^()]|\([^()]*\))+)\)\s*(?P<resto>.*)$'
)

# Formato 3: "1. CEBRASPE/MPS/2025 Enunciado..." -- número + cabeçalho SEM
# parênteses, seguido direto do enunciado na mesma linha. Cabeçalho aqui é
# só BANCA/ÓRGÃO/ANO (sempre com barra, observado nos PDFs reais), e o
# enunciado começa logo depois do ano. Captura até o token de ano (4
# dígitos), o resto da linha é enunciado.
PADRAO_INICIO_SEM_PARENTESE = re.compile(
    r'^(?P<numero>\d{1,3})\.\s+(?P<cabecalho>[A-ZÀ-Ú0-9][\w./\sÀ-Ú()]*?(?:19|20)\d{2})\s+(?P<resto>.*)$'
)

# Cabeçalho dentro do parêntese precisa "ter cara" de banca/concurso:
# ano de 4 dígitos no fim + pelo menos 1 separador (– , - ou /) entre campos.
# Separadores observados nos PDFs reais: "CESPE – ÓRGÃO – 2018" (travessão),
# "FGV - ÓRGÃO - 2023" (hífen), "FGV/TCE RR/2025" e "FCC / SEFAZ AP / 2022"
# (barra, com ou sem espaços ao redor). Texto extra após o ano é tolerado,
# separado por espaço OU barra (ex: "2013/Adaptada", "2006 Adaptada").
PADRAO_CABECALHO_VALIDO = re.compile(
    r'^[^–\-/]+[–\-/].+(19|20)\d{2}\s*[/\s]?\s*[\w()]*\s*$'
)

# Marcador de comentário: "Comentários" com ou sem dois-pontos, linha própria.
PADRAO_MARCADOR_COMENTARIO = re.compile(r'^Coment[aá]rios\s*:?\s*$', re.IGNORECASE)

# Marcador de gabarito: linha que COMEÇA com "Gabarito:" — usado apenas como
# pré-filtro rápido. A validação "é a linha inteira" (resolve Bloco F) é
# feita em detectar_marcador_gabarito, comparando contra o texto original.
PADRAO_GABARITO_INICIO = re.compile(r'^Gabarito\s*:\s*(?P<valor>.+)$', re.IGNORECASE)

# Alternativas de múltipla escolha: "a) texto" ou "(A) texto".
PADRAO_ALTERNATIVA = re.compile(
    r'^\(?(?P<letra>[A-Ea-e])\)\s*(?P<texto>.*)$'
)


# ---------------------------------------------------------------------------
# Detecção de início de questão (Bloco A, E, G)
# ---------------------------------------------------------------------------

# Cabeçalhos especiais que são válidos mesmo SEM banca/órgão/ano completos.
# Decisão do usuário: questão "Inédita" é categoria válida, não vai p/ revisão.
CABECALHOS_ESPECIAIS_VALIDOS = {"inédita", "inedita", "inédito", "inedito"}


def cabecalho_parece_valido(cabecalho_texto: str) -> bool:
    """
    Valida se o conteúdo dentro do parêntese tem cara de banca/concurso:
    ano de 4 dígitos no fim + separador entre campos.
    Resolve Bloco G (nota de rodapé "1 (Autor, 2010)" não bate nisso).

    Exceção: cabeçalhos especiais conhecidos (ex: "Inédita") são aceitos
    como válidos mesmo sem ano/separador.
    """
    texto = cabecalho_texto.strip()
    if texto.lower() in CABECALHOS_ESPECIAIS_VALIDOS:
        return True
    return bool(PADRAO_CABECALHO_VALIDO.match(texto))


def detectar_inicio_questao(linha: str, linha_seguinte: str):
    """
    Tenta reconhecer início de questão em três formatos observados:

      Formato 1 (mais comum):
        "1. (CESPE – ÓRGÃO – CARGO – 2018)"   -- tudo numa linha, com parênteses

      Formato 2 (provas FGV mais recentes):
        "1."                                   -- número sozinho
        "(FGV - ÓRGÃO - 2023)"                 -- cabeçalho na linha seguinte

      Formato 3 (CEBRASPE, alguns PDFs):
        "1. CEBRASPE/MPS/2025 Enunciado começa aqui..."
        -- número + cabeçalho SEM parênteses + enunciado na mesma linha

    Retorna um dict {numero, cabecalho_texto, linhas_consumidas, confianca,
    enunciado_inicial} ou None se não for início de questão.
    `enunciado_inicial` é o texto do enunciado que já vem na mesma linha
    do cabeçalho (só é não-vazio no Formato 3); o orquestrador deve
    prepend-ar isso ao enunciado da questão.

    `confianca` pode ser 'alta' (critérios completos batidos) ou
    'parcial' (bateu parte dos critérios, ex: tem ponto mas falta ano no
    cabeçalho) -- usado depois para sinalizar revisar=True (decisão do
    usuário sobre o caso hipotético do Bloco G).
    """
    linha = linha.strip()

    # --- Formato 1: número + cabeçalho (com parênteses) na mesma linha ---
    m = PADRAO_INICIO_MESMA_LINHA.match(linha)
    if m:
        numero = int(m.group("numero"))
        cabecalho = m.group("cabecalho").strip()
        # Tudo que sobra depois do ")" na mesma linha JÁ É início do
        # enunciado -- nos PDFs reais o texto costuma vir colado no
        # cabeçalho. (Correção do bug de perda do início do enunciado.)
        enunciado_inicial = linha[m.end():].strip()
        if cabecalho_parece_valido(cabecalho):
            return {
                "numero": numero,
                "cabecalho_texto": cabecalho,
                "linhas_consumidas": 1,
                "confianca": "alta",
                "enunciado_inicial": enunciado_inicial,
            }
        # Tem ponto, mas cabeçalho não convence (ex: falta ano, falta
        # separador). Não confundir com rodapé sem mais evidência, mas
        # também não aceitar cegamente -- sinaliza para revisão.
        return {
            "numero": numero,
            "cabecalho_texto": cabecalho,
            "linhas_consumidas": 1,
            "confianca": "parcial",
            "enunciado_inicial": enunciado_inicial,
        }

    # --- Formato 2: número sozinho, cabeçalho (com parênteses) na linha seguinte ---
    m2 = PADRAO_NUMERO_SOZINHO.match(linha)
    if m2 and linha_seguinte is not None:
        linha_seg = linha_seguinte.strip()
        # cabeçalho da linha seguinte deve estar entre parênteses.
        # Aceita parênteses ANINHADOS (ex.: "(FGV/AF (SEFAZ PR)/SEFAZ PR/2025)").
        m3 = PADRAO_CABECALHO_LINHA_SEGUINTE.match(linha_seg)
        if m3:
            numero = int(m2.group("numero"))
            cabecalho = m3.group("cabecalho").strip()
            enunciado_inicial = m3.group("resto").strip()
            if cabecalho_parece_valido(cabecalho):
                return {
                    "numero": numero,
                    "cabecalho_texto": cabecalho,
                    "linhas_consumidas": 2,
                    "confianca": "alta",
                    "enunciado_inicial": enunciado_inicial,
                }
            return {
                "numero": numero,
                "cabecalho_texto": cabecalho,
                "linhas_consumidas": 2,
                "confianca": "parcial",
                "enunciado_inicial": enunciado_inicial,
            }

    # --- Formato 3: número + cabeçalho SEM parênteses + enunciado, mesma linha ---
    m4 = PADRAO_INICIO_SEM_PARENTESE.match(linha)
    if m4:
        numero = int(m4.group("numero"))
        cabecalho = m4.group("cabecalho").strip()
        resto = m4.group("resto").strip()
        # cabecalho aqui já garante ano (regex exige), só falta checar
        # separador (banca/orgao) -- reaproveita a mesma validação.
        if cabecalho_parece_valido(cabecalho):
            return {
                "numero": numero,
                "cabecalho_texto": cabecalho,
                "linhas_consumidas": 1,
                "confianca": "alta",
                "enunciado_inicial": resto,
            }
        return {
            "numero": numero,
            "cabecalho_texto": cabecalho,
            "linhas_consumidas": 1,
            "confianca": "parcial",
            "enunciado_inicial": resto,
        }

    return None


# ---------------------------------------------------------------------------
# Detecção de marcador de comentário (Bloco B)
# ---------------------------------------------------------------------------

def detectar_marcador_comentario(linha: str) -> bool:
    """'Comentários' ou 'Comentários:' sozinha na linha, com ou sem dois-pontos."""
    return bool(PADRAO_MARCADOR_COMENTARIO.match(linha.strip()))


# ---------------------------------------------------------------------------
# Detecção de marcador de gabarito (Bloco F - caso crítico)
# ---------------------------------------------------------------------------

def detectar_marcador_gabarito(linha: str):
    """
    Reconhece o marcador REAL de gabarito (fim de questão).

    Regra (resolve Bloco F): a linha, depois de strip(), precisa começar
    com "Gabarito:" e ser -- na prática -- a linha inteira (cabeçalho +
    valor, sem mais nada de texto corrido em volta). Isso diferencia do
    caso em que "Gabarito: errada." aparece embutido no MEIO de uma frase
    de citação dentro do comentário (ex: '...Cito a questão: "...
    Gabarito: errada." Voltando à questão atual...').

    Heurística prática usada: a linha tratada (strip) deve bater
    integralmente com o padrão "Gabarito: <valor curto>", sem texto
    adicional depois do valor que pareça continuação de frase (ex.
    terminar em letra minúscula seguida de mais palavras). Como o valor
    do gabarito é sempre curto (uma letra ou "correta"/"errada"), basta
    exigir que a linha INTEIRA seja o marcador.

    Retorna o valor do gabarito (str) ou None.
    """
    linha_stripped = linha.strip()
    m = PADRAO_GABARITO_INICIO.match(linha_stripped)
    if not m:
        return None
    valor = m.group("valor").strip()
    # Defesa extra: se o "valor" for suspeitosamente longo (mais de ~6
    # palavras), provavelmente não é um marcador de gabarito real, e sim
    # uma citação dentro de um parágrafo maior que por acaso começa com
    # "Gabarito:". Nesse caso, não reconhece como marcador aqui --
    # quem decide o que fazer com isso é a camada de cima (parsear_questoes_do_bloco),
    # que sinaliza revisar=True quando o comentário não conseguiu fechar
    # de forma inequívoca.
    if len(valor.split()) > 6:
        return None
    return valor


def normalizar_valor_gabarito(valor_gabarito: str) -> str:
    """
    Limpa o valor bruto do gabarito antes de classificar/armazenar:
    remove aspas (héteis, retas ou curvas) e ponto final.
    Ex.: '"C".' -> 'C'   |   'Letra A.' -> 'Letra A'
    """
    valor = valor_gabarito.strip()
    valor = valor.strip('"\u201c\u201d\'')
    valor = valor.strip()
    valor = valor.rstrip('.')
    valor = valor.strip('"\u201c\u201d\'')
    return valor.strip()


def inferir_tipo_gabarito(valor_gabarito: str):
    """
    Classifica o valor do gabarito em 'certo_errado' ou 'multipla_escolha'.
    Retorna None se não reconhecer o padrão (sinaliza para revisão).

    Tolera ponto final ("Letra A.") e aspas ('"C".') no valor bruto --
    normaliza antes de comparar (resolve variações reais encontradas nos
    PDFs do Estratégia Concursos).

    NOTA: gabarito Certo/Errado sempre vem por extenso ("Certo"/"Certa"/
    "Errado"/"Errada"/variações) nos PDFs reais -- nunca como letra
    isolada "C"/"E". Por isso "C" e "E" sozinhos são tratados como letra
    de múltipla escolha, não como atalho de Certo/Errado (evita colisão
    com gabarito "C" ou "E" de questão A-E).
    """
    valor_norm = normalizar_valor_gabarito(valor_gabarito).lower()
    if valor_norm in ("certa", "certo", "correta", "correto",
                      "verdadeiro", "verdadeira"):
        return "certo_errado"
    if valor_norm in ("errada", "errado", "incorreta", "incorreto",
                      "falso", "falsa"):
        return "certo_errado"
    if re.match(r'^letra\s+[a-e]$', valor_norm):
        return "multipla_escolha"
    if re.match(r'^[a-e]$', valor_norm):
        return "multipla_escolha"
    return None


# ---------------------------------------------------------------------------
# Extração do cabeçalho (banca / órgão / cargo / ano) - Bloco A vs C
# ---------------------------------------------------------------------------

# Bancas organizadoras conhecidas. Usadas para decidir QUAL campo do
# cabeçalho é a banca, já que a ordem varia entre PDFs:
#   "SEFAZ-PA/UEPA/2013"  -> ordem ÓRGÃO/BANCA/ANO (banca = UEPA)
#   "CEBRASPE/MPS/2025"   -> ordem BANCA/ÓRGÃO/ANO (banca = CEBRASPE)
# Em vez de assumir posição, procuramos o campo que casa com esta lista.
BANCAS_CONHECIDAS = (
    "CEBRASPE", "CESPE", "FGV", "FCC", "ESAF", "VUNESP", "CESGRANRIO",
    "FEPESE", "UEPA", "IBFC", "QUADRIX", "AOCP", "IADES", "FUNDEP",
    "IDECAN", "CONSULPLAN", "FUNCAB", "FUMARC", "FCM", "AVANÇA SP",
    "INSTITUTO ACCESS", "SELECON", "IBADE", "FUNDATEC",
)


def _eh_banca_conhecida(texto: str) -> bool:
    t = texto.upper()
    return any(banca in t for banca in BANCAS_CONHECIDAS)


def extrair_cabecalho(cabecalho_texto: str):
    """
    Separa o conteúdo do parêntese (ou do texto solto, Formato 3) em
    banca / orgao / cargo / ano.

    Separadores observados nos PDFs reais (nessa ordem de prioridade):
      1. barra "/"      -> "FGV/TCE RR/2025", "FCC / SEFAZ AP / 2022"
      2. travessão "–"  -> "CESPE – ÓRGÃO – ANALISTA – 2018"
      3. hífen "-"      -> "FGV - ÓRGÃO - 2023"

    IMPORTANTE: barra é tentada primeiro porque a própria banca pode
    conter hífen interno (ex: "SEFAZ-PA", "SEFAZ-SP", "SEFAZ-DF"). Se o
    separador escolhido fosse sempre –/-, "SEFAZ-PA/UEPA/2013" quebraria
    errado (cortaria "SEFAZ" e "PA/UEPA/2013" em vez de "SEFAZ-PA" e
    "UEPA" e "2013"). Quando há "/" no texto, ele é o separador correto;
    o hífen interno de "SEFAZ-PA" é então preservado como parte do campo.

    Texto extra após o ano (ex: "2006/Adaptada", "2013/Adaptada") é
    descartado do campo ano em si, mas não quebra o parsing.

    Exemplos:
      "CESPE – LOREM ÓRGÃO – ANALISTA – 2018" -> 4 campos (–)
      "LOREM BANCA – LOREM ÓRGÃO – 2018"      -> 3 campos (–)
      "FGV - LOREM ÓRGÃO - 2023"              -> 3 campos (-)
      "FGV/TCE RR/2025"                        -> 3 campos (/)
      "FCC / SEFAZ AP / 2022"                  -> 3 campos (/)
      "SEFAZ-PA/UEPA/2013/Adaptada"            -> 3 campos (/), banca='SEFAZ-PA'
    """
    cabecalho_texto = cabecalho_texto.strip()

    if "/" in cabecalho_texto:
        partes = [p.strip() for p in cabecalho_texto.split("/") if p.strip()]
    else:
        partes = [p.strip() for p in re.split(r'[–-]', cabecalho_texto) if p.strip()]

    banca = orgao = cargo = ano = None

    if not partes:
        return {"banca": None, "orgao": None, "cargo": None, "ano": None}

    # Acha o PRIMEIRO campo (da direita pra esquerda) que contém um ano de
    # 4 dígitos -- normalmente é o último campo, mas pode vir seguido de
    # uma observação tipo "2013/Adaptada" (já seria outro campo nesse caso
    # por causa do split em "/", então o campo do ano fica isolado).
    idx_ano = None
    for idx in range(len(partes) - 1, -1, -1):
        m_ano = re.search(r'(19|20)\d{2}', partes[idx])
        if m_ano:
            ano = int(m_ano.group(0))
            idx_ano = idx
            break

    if idx_ano is not None:
        partes_campos = partes[:idx_ano]
    else:
        partes_campos = partes

    # Atribuição banca/órgão/cargo:
    # 1º) se algum campo casa com banca conhecida, ELE é a banca (e o
    #     restante vira órgão/cargo na ordem em que aparece). Resolve a
    #     inconsistência de ordem entre PDFs.
    # 2º) se nenhum casar (banca desconhecida ou "Inédita"), cai no
    #     comportamento posicional antigo (1º=banca, 2º=órgão, 3º=cargo).
    idx_banca = None
    for j, parte in enumerate(partes_campos):
        if _eh_banca_conhecida(parte):
            idx_banca = j
            break

    if idx_banca is not None:
        banca = partes_campos[idx_banca]
        restantes = [p for k, p in enumerate(partes_campos) if k != idx_banca]
        if len(restantes) >= 1:
            orgao = restantes[0]
        if len(restantes) >= 2:
            cargo = restantes[1]
    else:
        if len(partes_campos) >= 1:
            banca = partes_campos[0]
        if len(partes_campos) >= 2:
            orgao = partes_campos[1]
        if len(partes_campos) >= 3:
            cargo = partes_campos[2]

    return {"banca": banca, "orgao": orgao, "cargo": cargo, "ano": ano}


# ---------------------------------------------------------------------------
# Alternativas (múltipla escolha)
# ---------------------------------------------------------------------------

def linha_eh_alternativa(linha: str):
    """Retorna (letra, texto) se a linha for uma alternativa a)-e), senão None."""
    m = PADRAO_ALTERNATIVA.match(linha.strip())
    if m:
        return m.group("letra").upper(), m.group("texto")
    return None


# ---------------------------------------------------------------------------
# Orquestrador: percorre um bloco e monta as questões individuais
# ---------------------------------------------------------------------------

def gerar_id_unico(nome_arquivo: str, inicio_linha_bloco: int, numero_questao: int) -> str:
    """
    ID único da questão (decisão do usuário): arquivo + inicio_linha do
    bloco (já é único, vem da etapa 1) + número da questão dentro do bloco.
    Resolve Bloco D (numeração reinicia a cada novo bloco).
    """
    return f"{nome_arquivo}::bloco{inicio_linha_bloco}::q{numero_questao}"


def parsear_questoes_do_bloco(texto_bloco: str, nome_arquivo: str, inicio_linha_bloco: int):
    """
    Recebe o texto bruto de UM bloco "questoes_comentadas" (já delimitado
    pela etapa 1) e devolve uma lista de dicts, uma por questão encontrada.

    Cada dict tem os campos que vão para a tabela questoes_banco:
      numero_questao, banca, orgao, cargo, ano, enunciado,
      alternativa_a..e, gabarito, tipo_gabarito, comentario,
      id_unico_questao, revisar, motivo_revisao
    """
    linhas = texto_bloco.split("\n")
    n = len(linhas)

    questoes = []
    i = 0
    questao_atual = None

    def nova_questao(numero, cabecalho_texto, confianca):
        campos = extrair_cabecalho(cabecalho_texto)
        revisar = False
        motivos = []
        if confianca == "parcial":
            revisar = True
            motivos.append("cabecalho_de_questao_incompleto_ou_atipico")
        return {
            "numero_questao": numero,
            "banca": campos["banca"],
            "orgao": campos["orgao"],
            "cargo": campos["cargo"],
            "ano": campos["ano"],
            "enunciado_linhas": [],
            "alternativas": {},
            "comentario_linhas": [],
            "gabarito": None,
            "tipo_gabarito": None,
            "id_unico_questao": gerar_id_unico(nome_arquivo, inicio_linha_bloco, numero),
            "revisar": revisar,
            "motivo_revisao": motivos,
            "_fase": "enunciado",  # enunciado -> alternativas -> comentario -> fechada
            "_alt_atual": None,    # letra da alternativa em construção (multi-linha)
        }

    def fechar_questao(q):
        # BUG-3: as quebras de linha dentro do enunciado são quebras visuais do
        # PDF (não de parágrafo). Junta tudo num parágrafo só, colapsando
        # qualquer sequência de espaços/quebras em um único espaço.
        q["enunciado"] = re.sub(r"\s+", " ", " ".join(q["enunciado_linhas"])).strip()
        # Comentário preserva estrutura de parágrafos (ainda não exibido; F2).
        q["comentario"] = "\n".join(q["comentario_linhas"]).strip() if q["comentario_linhas"] else None
        for letra in "ABCDE":
            alt = q["alternativas"].get(letra)
            if alt is not None:
                # Normaliza espaços/quebras internas da alternativa multi-linha.
                alt = re.sub(r"\s+", " ", alt).strip()
            q[f"alternativa_{letra.lower()}"] = alt

        # Questão sem gabarito identificado: sinaliza para revisão, não descarta.
        if q["gabarito"] is None:
            q["revisar"] = True
            q["motivo_revisao"].append("gabarito_nao_identificado")

        # tipo_gabarito não reconhecido: sinaliza.
        if q["gabarito"] is not None and q["tipo_gabarito"] is None:
            q["revisar"] = True
            q["motivo_revisao"].append("tipo_gabarito_nao_reconhecido")

        q["motivo_revisao"] = "; ".join(q["motivo_revisao"]) if q["motivo_revisao"] else None
        for chave in ("enunciado_linhas", "alternativas", "comentario_linhas", "_fase", "_alt_atual"):
            q.pop(chave, None)
        return q

    while i < n:
        linha = linhas[i]
        linha_seguinte = linhas[i + 1] if i + 1 < n else None

        inicio = detectar_inicio_questao(linha, linha_seguinte)
        if inicio is not None:
            # Fecha a questão anterior, se houver (vira a próxima questão,
            # delimitando o fim da anterior).
            if questao_atual is not None:
                questoes.append(fechar_questao(questao_atual))

            questao_atual = nova_questao(
                inicio["numero"], inicio["cabecalho_texto"], inicio["confianca"]
            )
            if inicio.get("enunciado_inicial"):
                questao_atual["enunciado_linhas"].append(inicio["enunciado_inicial"])
            i += inicio["linhas_consumidas"]
            continue

        if questao_atual is None:
            # Ainda não entramos em nenhuma questão (ex: linha do heading
            # "QUESTÕES COMENTADAS" ou linha em branco antes da primeira
            # questão). Ignora.
            i += 1
            continue

        # --- dentro de uma questão já aberta ---

        if questao_atual["_fase"] == "enunciado":
            alt = linha_eh_alternativa(linha)
            if alt is not None:
                # primeira alternativa: encerra o enunciado e entra na fase
                # de alternativas (a partir daqui, linhas sem letra são
                # continuação da alternativa atual, não enunciado).
                letra, texto_alt = alt
                questao_atual["alternativas"][letra] = texto_alt.strip()
                questao_atual["_alt_atual"] = letra
                questao_atual["_fase"] = "alternativas"
                i += 1
                continue
            if detectar_marcador_comentario(linha):
                questao_atual["_fase"] = "comentario"
                i += 1
                continue
            # BUG-2: descarta linha que é só um número curto (número de página
            # solto que sobrou no meio do enunciado) e linhas vazias.
            linha_strip = linha.strip()
            if not linha_strip or re.match(r"^\d{1,4}$", linha_strip):
                i += 1
                continue
            questao_atual["enunciado_linhas"].append(linha)
            i += 1
            continue

        if questao_atual["_fase"] == "alternativas":
            if detectar_marcador_comentario(linha):
                questao_atual["_fase"] = "comentario"
                i += 1
                continue
            alt = linha_eh_alternativa(linha)
            if alt is not None:
                # nova alternativa (b, c, ...): passa a ser a alternativa atual.
                letra, texto_alt = alt
                questao_atual["alternativas"][letra] = texto_alt.strip()
                questao_atual["_alt_atual"] = letra
                i += 1
                continue
            # Linha sem letra dentro da fase de alternativas = continuação
            # da alternativa atual (alternativa quebrada em várias linhas).
            # Ignora linhas vazias e números de página soltos (ex: "53").
            linha_strip = linha.strip()
            if linha_strip and not re.match(r'^\d{1,4}$', linha_strip):
                letra_atual = questao_atual["_alt_atual"]
                if letra_atual is not None:
                    atual = questao_atual["alternativas"].get(letra_atual, "")
                    questao_atual["alternativas"][letra_atual] = (atual + " " + linha_strip).strip()
                else:
                    # sem alternativa atual (não deveria ocorrer): preserva no enunciado
                    questao_atual["enunciado_linhas"].append(linha)
            i += 1
            continue

        if questao_atual["_fase"] == "comentario":
            valor_gabarito = detectar_marcador_gabarito(linha)
            if valor_gabarito is not None:
                questao_atual["gabarito"] = normalizar_valor_gabarito(valor_gabarito)
                questao_atual["tipo_gabarito"] = inferir_tipo_gabarito(valor_gabarito)
                questao_atual["_fase"] = "fechada"
                i += 1
                continue
            questao_atual["comentario_linhas"].append(linha)
            i += 1
            continue

        # _fase == "fechada": lixo entre o gabarito e a próxima questão
        # (rodapés de página, "Aula 07", marca d'água, numeração de
        # página etc. -- já presentes no dataset real). Ignora até achar
        # a próxima questão.
        i += 1

    # fim do texto: fecha a última questão em aberto (Bloco H)
    if questao_atual is not None:
        questoes.append(fechar_questao(questao_atual))

    return questoes
