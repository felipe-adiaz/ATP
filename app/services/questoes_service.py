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
4. Cada questão começa com um número seguido de ponto (ex: "01.", "1.") e geralmente traz a origem entre parênteses logo em seguida, em formatos como (BANCA/ÓRGÃO/ANO), (BANCA – ÓRGÃO – ANO), (BANCA/ÓRGÃO/ANO/Adaptada) ou similar — a ordem entre banca e órgão pode variar. Esse parêntese pode estar ausente; nesse caso deixe banca, orgao e ano como null.
5. A seção pode estar dividida em subseções por banca (ex: "CEBRASPE/CESPE", "Outras Bancas"). Nesses casos a numeração pode reiniciar a cada subseção — ignore isso e numere as questões sequencialmente ao longo de TODA a seção, na ordem em que aparecem no texto.
6. As alternativas podem vir em formatos diferentes: "a)", "A)" ou "(A)". Trate todos da mesma forma, sempre mapeando para os campos alternativa_a a alternativa_e.
7. O texto pode conter marcações de destaque do tipo ==texto== — trate como texto normal, ignore os símbolos ==.
8. O texto pode conter quebras de página no meio de uma questão, no formato "--- ## Página N" — ignore essas quebras, a questão continua.
9. O comentário é o texto explicativo que vem após "Comentários:" (ou "Comentários", sem dois-pontos) e antes da próxima questão ou do fim da seção.
10. O gabarito normalmente aparece como "Gabarito: Letra X" ou similar. Extraia apenas a letra. Se o gabarito não estiver explícito em nenhum lugar do texto da questão, deixe como null — NUNCA infira ou adivinhe o gabarito a partir do comentário.
11. Se a seção "Questões Comentadas" não existir no texto recebido, retorne uma lista vazia.

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
    Corta no início da próxima seção de nível equivalente, o que vier primeiro.
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
    """Conta padrão 'número + ponto + parêntese' como checagem independente da IA."""
    padrao = re.compile(r"\b\d{1,3}\.\s*\(")
    return len(padrao.findall(trecho))


def extrair_questoes_via_ia(trecho: str) -> list[dict]:
    """Chama a IA para extrair as questões estruturadas do trecho isolado."""
    resposta = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": PROMPT_SISTEMA},
            {"role": "user", "content": trecho},
        ],
    )
    conteudo = resposta.choices[0].message.content
    dados = json.loads(conteudo)
    return dados.get("questoes", [])


def processar_extracao(markdown: str) -> dict:
    """
    Função principal: recebe o markdown de uma aula já salvo em pdf_processados,
    retorna o resultado pronto para persistir em extracoes_questoes + questoes_banco.
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
            "questoes": [],
        }

    total_esperado = contar_questoes_esperadas(trecho)
    questoes = extrair_questoes_via_ia(trecho)
    total_extraido = len(questoes)

    status = "ok" if total_extraido == total_esperado else "revisar"

    return {
        "conteudo_hash": hash_conteudo,
        "status": status,
        "total_questoes": total_extraido,
        "total_esperado": total_esperado,
        "texto_origem": trecho,
        "questoes": questoes,
    }
