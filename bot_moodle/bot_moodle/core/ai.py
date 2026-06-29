"""Integração com o Gemini — geração de respostas e sanitização."""

import re
from google import genai


def criar_cliente(api_key: str) -> genai.Client:
    """Cria e retorna um cliente Gemini autenticado."""
    return genai.Client(api_key=api_key)


def sanitizar_resposta(texto: str) -> str:
    """Converte #include <x> → #include [x] para não quebrar HTML no navegador."""
    return re.sub(r"#include\s*<([^>]+)>", r"#include [\1]", texto)


def pedir_ao_gemini(
    cliente: genai.Client,
    pergunta: str,
    contexto_historico: str = "",
    modo_fix: bool = False,
) -> str:
    """
    Envia prompt ao Gemini com fallback entre modelos.

    Args:
        cliente: instância autenticada do genai.Client.
        pergunta: texto da pergunta ou código a corrigir.
        contexto_historico: bloco de contexto anterior (opcional).
        modo_fix: se True, usa instrução de debugging em vez de tutoria.

    Returns:
        Resposta da IA sanitizada, ou mensagem de cota esgotada.
    """
    modelos_fallback = [
        "gemini-3.5-flash", "gemini-3-flash", "gemini-2.5-flash",
        "gemini-3.1-flash-lite", "gemini-2.5-flash-lite",
    ]

    if modo_fix:
        instrucao = (
            "Você é um especialista em debugging e correção de código. "
            "Identifique o erro de sintaxe ou lógica, corrija o código "
            "e forneça a resposta de forma extremamente direta."
        )
    else:
        instrucao = (
            "Você é um tutor acadêmico de programação. "
            "Forneça explicações diretas caso solicitado e, "
            "caso não tenha sido solicitada explicação, "
            "forneça apenas a resposta direta."
        )

    prompt = (
        "Você é um tutor acadêmico de programação especializado em Ciência da Computação.\n"
        f"{instrucao}\n\n"
        "REGRA CRÍTICA DE FORMATAÇÃO:\n"
        "Responda APENAS em texto puro (Plain Text). "
        "NÃO use nenhuma formatação Markdown (.md).\n"
        "NÃO use asteriscos para negrito (**), "
        "NÃO use blocos de código com crases (```c) e NÃO use #.\n"
        "Se houver código em C, apenas pule uma linha e escreva o código "
        "diretamente com identação normal.\n\n"
    )
    if contexto_historico:
        prompt += (
            f"CONTEXTO DE MENSAGENS ANTERIORES:\n{contexto_historico}\n---------\n"
        )
    prompt += f"SOLICITAÇÃO ATUAL: {pergunta}"

    for modelo in modelos_fallback:
        try:
            print(f"[IA] Tentando modelo: {modelo}...")
            response = cliente.models.generate_content(
                model=modelo, contents=prompt
            )
            print(f"[IA] ✨ Sucesso com: {modelo}")
            return sanitizar_resposta(response.text)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            print(f"⚠️ {modelo} falhou: {exc}")

    return "Desculpe, a cota gratuita de todos os modelos foi excedida. 🤖"
