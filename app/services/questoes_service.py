import hashlib
import json
import os
import re

from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

PROMPT_SISTEMA = """Você extrai questões de concursos públicos a partir de um texto em markdown.

REGRAS:
1. Extraia APENAS questões que estejam dentro da seção "Questões Comentadas".
2. Ignore completamente qualquer seção "Lista de Questões" (são as mesmas questões, repetidas, sem comentário).
3. Ignore questões soltas que apareçam misturadas no meio do conteúdo teórico, fora da seção "Questões Comentadas".
4. Cada questão começa com um número seguido de ponto (ex: "01.", "1.") e geralmente traz a origem entre parênteses logo em seguida, em formatos como (BANCA/ÓRGÃO/ANO), (BANCA – ÓRGÃO – ANO), (BANCA/ÓRGÃO/ANO/Adaptada) ou similar. Esse parêntese pode estar ausente; nesse caso deixe banca, orgao e ano como null.
5. A seção pode estar dividida em subseções por banca (ex: "CEBRASPE/CESPE", "Outras Bancas"). Nesses casos a numeração pode reiniciar a cada subseção — ignore isso e numere as questões sequencialmente ao longo de TODO o texto recebido, na ordem em que aparecem.
6. As alternativas podem vir em formatos diferentes: "a)", "A)" ou "(A)". Trate todos da mesma forma, sempre mapeando para os campos alternativa_a a alternativa_e.
7. O texto pode conter marcações de destaque do tipo ==texto== — trate como texto normal, ignore os símbolos ==.
8. O texto pode conter quebras de página no meio de uma questão, no formato "--- ## Página N" — ignore essas quebras, a questão continua.
9. O comentário é o texto explicativo que vem após "Comentários:" (ou "Comentários", sem dois-pontos) e antes da próxima questão ou do fim do texto.
10. O gabarito normalmente aparece como "Gabarito: Letra X" ou similar. Extraia apenas a letra. Se o gabarito não estiver explícito em nenhum lugar do texto da questão, use o valor JSON null (sem aspas) — NUNCA escreva a palavra "null" como texto entre aspas, e NUNCA infira ou adivinhe o gabarito a partir do comentário.
11. Se nenhuma questão estiver presente no texto recebido, retorne uma lista vazia.
12. Para QUALQUER campo que não tiver valor (banca, orgao, ano, qualquer alternativa, gabarito, comentario), use sempre o valor JSON null (sem aspas), nunca a string "null" nem texto vazio "".
13. Extraia o comentário completo, sem resumir ou abreviar, mesmo que seja longo. Não pule questões para economizar espaço — extraia TODAS as questões presentes no texto recebido, do início ao fim, mesmo que sejam várias.

Responda APENAS com um JSON válido, sem texto antes ou depois, sem marcação de código, no formato:

{
  "questoes": [
    {
      "numero_questao": 1,
      "banca": "FCC ou null",
      "orgao": "SEFAZ-PA ou null",
      "ano": 2013,
      "enunciado": "...",
      "alternativa_a": "... ou null",
      "alternativa_b": "... ou null",
      "alternativa_c": "... ou null",
      "alternativa_d": "... ou null",
      "alternativa_e": "... ou null",
      "gabarito": "A ou null",
      "comentario": "... ou null"
    }
  ]
}"""


def calcular_hash(texto: str) -> str:
    """Hash SHA-256 do conteúdo, usado como chave de cache de extração."""
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def localizar_secao_questoes(markdown: str) -> str | None:
    """
    Localiza o trecho da seção 'Questões Comentadas' dentro do markdown completo.
    Busca direto no corpo do texto (não depende de sumário, que nem sempre é confiável).
    Corta no início da próxima seção de nível equivalente (ex: 'Gabarito' isolado,
    ou fim do documento), o que vier primeiro.
    """
    padrao_inicio = re.compile(r"quest[õo]es\s+comentadas", re.IGNORECASE)
    match_inicio = padrao_inicio.search(markdown)
    if not match_inicio:
        return None

    inicio = match_inicio.start()

    padrao_fim = re.compile(
        r"\n\s*lista\s+de\s+quest[õo]es\s*\n|\n\s*#+\s*gabarito\s*\n",
        re.IGNORECASE,
    )
    match_fim = padrao_fim.search(markdown, pos=inicio + 50)

    fim = match_fim.start() if match_fim else len(markdown)
    return markdown[inicio:fim]


def contar_questoes_esperadas(trecho: str) -> int:
    """
    Conta ocorrências do padrão 'número + ponto + parêntese contendo um ano
    de 4 dígitos' para ter uma estimativa independente da IA de quantas
    questões existem no trecho. Exigir o ano evita falsos positivos como
    'Art. 25. (par. 1o)' no meio de comentários, que não são questões.
    """
    padrao = re.compile(r"\d{1,3}\.\s*\([^)]*(?:19|20)\d{2}[^)]*\)")
    return len(padrao.findall(trecho))


def dividir_em_lotes(trecho: str, questoes_por_lote: int = 6) -> list[str]:
    """
    Divide o trecho da seção de questões em lotes menores, cortando nos
    pontos onde uma nova questão começa (mesmo padrão usado em
    contar_questoes_esperadas, com ano de 4 dígitos exigido no parêntese
    para não confundir com referências de lei tipo 'Art. 25. (par. 1o)').
    Isso evita que o modelo perca qualidade/aderência ao processar um trecho
    muito longo de uma vez.
    """
    padrao = re.compile(r"\d{1,3}\.\s*\([^)]*(?:19|20)\d{2}[^)]*\)")
    posicoes_inicio = [m.start() for m in padrao.finditer(trecho)]

    if not posicoes_inicio:
        return [trecho]

    lotes = []
    for i in range(0, len(posicoes_inicio), questoes_por_lote):
        inicio_lote = posicoes_inicio[i]
        indice_fim = i + questoes_por_lote
        fim_lote = posicoes_inicio[indice_fim] if indice_fim < len(posicoes_inicio) else len(trecho)
        lotes.append(trecho[inicio_lote:fim_lote])

    return lotes


def extrair_questoes_via_ia(trecho: str) -> dict:
    """
    Chama a IA para extrair as questões estruturadas de um lote (trecho menor).
    Retorna a lista de questões parseadas, o texto bruto da resposta e o
    motivo do término — para diagnóstico de truncamento.
    """
    resposta = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        max_tokens=16000,
        messages=[
            {"role": "system", "content": PROMPT_SISTEMA},
            {"role": "user", "content": trecho},
        ],
    )
    conteudo = resposta.choices[0].message.content
    motivo_termino = resposta.choices[0].finish_reason

    try:
        dados = json.loads(conteudo)
        questoes = dados.get("questoes", [])
        erro_parsing = None
    except json.JSONDecodeError as e:
        questoes = []
        erro_parsing = str(e)

    return {
        "questoes": questoes,
        "resposta_bruta": conteudo,
        "motivo_termino": motivo_termino,
        "erro_parsing": erro_parsing,
    }


def processar_extracao(markdown: str) -> dict:
    """
    Função principal: recebe o markdown de uma aula já salvo em pdf_processados,
    retorna o resultado pronto para persistir em extracoes_questoes + questoes_banco.

    Processa a seção de questões em lotes menores (em vez de mandar tudo de
    uma vez), porque trechos muito longos fazem o modelo perder aderência à
    instrução e pular questões silenciosamente, mesmo sem truncar tecnicamente.
    """
    hash_conteudo = calcular_hash(markdown)

    trecho = localizar_secao_questoes(markdown)
    if trecho is None:
        return {
            "conteudo_hash": hash_conteudo,
            "status": "sem_secao",
            "total_questoes": 0,
            "total_esperado": 0,
            "texto_origem": None,
            "resposta_bruta_ia": None,
            "lotes_entrada_debug": None,
            "motivo_termino": None,
            "questoes": [],
        }

    total_esperado = contar_questoes_esperadas(trecho)
    lotes = dividir_em_lotes(trecho, questoes_por_lote=6)

    todas_questoes = []
    todas_respostas_brutas = []
    todos_lotes_entrada = []
    motivos_termino = []
    houve_erro_parsing = False

    for lote in lotes:
        resultado_ia = extrair_questoes_via_ia(lote)
        todas_questoes.extend(resultado_ia["questoes"])
        todas_respostas_brutas.append(resultado_ia["resposta_bruta"])
        todos_lotes_entrada.append(lote)
        motivos_termino.append(resultado_ia["motivo_termino"])
        if resultado_ia["erro_parsing"]:
            houve_erro_parsing = True

    # Renumera sequencialmente, já que cada lote conta do zero internamente.
    for indice, questao in enumerate(todas_questoes, start=1):
        questao["numero_questao"] = indice

    total_extraido = len(todas_questoes)

    if houve_erro_parsing:
        status = "erro_parsing"
    elif any(motivo != "stop" for motivo in motivos_termino):
        status = "truncado"
    elif total_extraido == total_esperado:
        status = "ok"
    else:
        status = "revisar"

    return {
        "conteudo_hash": hash_conteudo,
        "status": status,
        "total_questoes": total_extraido,
        "total_esperado": total_esperado,
        "texto_origem": trecho,
        "resposta_bruta_ia": "\n---LOTE---\n".join(todas_respostas_brutas),
        "lotes_entrada_debug": "\n---LOTE---\n".join(todos_lotes_entrada),
        "motivo_termino": ",".join(motivos_termino),
        "questoes": todas_questoes,
    }
