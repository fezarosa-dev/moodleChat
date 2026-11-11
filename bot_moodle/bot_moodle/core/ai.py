"""Integração com IA (Claude Code local, Gemini de reserva) — geração de respostas e sanitização."""

import re
import subprocess
import tempfile
from typing import Any

from google import genai


def criar_cliente(api_key: str) -> "genai.Client | None":
    """Cria o cliente Gemini (reserva). None sem chave: bot usa só o Claude."""
    return genai.Client(api_key=api_key) if api_key else None


def sanitizar_resposta(texto: str) -> str:
    """Converte #include <x> → #include [x] para não quebrar HTML no navegador."""
    return re.sub(r"#include\s*<([^>]+)>", r"#include [\1]", texto)


# Claude via CLI do Claude Code logado na máquina (usa a cota do plano, sem API key).
# Roda como agente numa pasta temporária: escreve, compila e testa o código antes de responder.
# Precisa do gcc no PATH (no Silverblue, rode o backend dentro de uma distrobox com gcc).
_INSTRUCAO_VERIFICAR = (
    "Se a sua resposta contiver código C, você DEVE testá-lo antes de responder:\n"
    "1. Salve o código em main.c nesta pasta (Write).\n"
    "2. Compile: gcc -Wall -Wextra -g -fsanitize=address,undefined -o prog main.c -lm\n"
    "   (se os sanitizers não linkarem, compile sem -fsanitize).\n"
    "3. Rode com casos de teste, incluindo bordas: printf 'entrada\\n' | ./prog\n"
    "4. Corrija até compilar sem avisos e dar a saída esperada em todos os casos.\n"
    "Use UM comando simples por chamada do Bash (sem &&, ;, for, while, caminhos absolutos).\n"
    "A resposta final é só o texto para o aluno, seguindo as regras de formatação da mensagem."
)
CLAUDE_CMD = [
    "claude", "-p",
    "--model", "opus",
    "--effort", "medium",
    "--tools", "Bash,Write,Read,Edit",
    # Arquivos só dentro da pasta temporária; Bash só gcc, o binário e printf para entrada.
    # ponytail: ./prog executa código arbitrário (igual ao !run) e a distrobox compartilha a home;
    # isolar de verdade exigiria container sem home/rede.
    "--allowedTools",
    "Write(./**)", "Edit(./**)", "Read(./**)",
    "Bash(gcc *)", "Bash(./prog*)", "Bash(printf *)",
    "--setting-sources", "",     # ignora hooks/CLAUDE.md/config do usuário
    "--strict-mcp-config",       # sem servidores MCP
    "--no-session-persistence",  # não polui o histórico de sessões
    "--system-prompt", _INSTRUCAO_VERIFICAR,
]
CLAUDE_TIMEOUT_S = 300


def _pedir_ao_claude(prompt: str) -> "str | None":
    """Roda `claude -p` com o prompt no stdin. None em qualquer falha (cai no Gemini)."""
    try:
        with tempfile.TemporaryDirectory(prefix="bot_moodle_") as pasta:
            proc = subprocess.run(
                CLAUDE_CMD,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=CLAUDE_TIMEOUT_S,
                cwd=pasta,  # área de trabalho isolada por pedido, longe de CLAUDE.md
                check=False,
            )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"⚠️ Claude falhou: {exc}")
        return None
    saida = proc.stdout.strip()
    if proc.returncode != 0 or not saida:
        print(f"⚠️ Claude falhou (exit {proc.returncode}): {proc.stderr.strip() or saida}")
        return None
    return saida


def pedir_a_ia(
    cliente: "genai.Client | None",
    pergunta: str,
    contexto_historico: str = "",
    modo_fix: bool = False,
) -> str:
    """
    Envia prompt ao Claude (CLI local); se falhar, tenta os modelos Gemini.

    Args:
        cliente: instância do genai.Client (usada só no fallback).
        pergunta: texto da pergunta ou código a corrigir.
        contexto_historico: conversa anterior (perguntas, respostas e runs).
        modo_fix: se True, usa instrução de debugging em vez de tutoria.

    Returns:
        Resposta da IA sanitizada, ou mensagem de cota esgotada.
    """
    modelos_fallback = [
        "gemini-3.5-flash",
        "gemini-3-flash",
        "gemini-2.5-flash",
        "gemini-3.1-flash-lite",
        "gemini-2.5-flash-lite",
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
            "CONVERSA ATÉ AQUI (mais antiga primeiro; use como contexto):\n"
            f"{contexto_historico}\n---------\n"
        )
    prompt += f"SOLICITAÇÃO ATUAL: {pergunta}"

    print("[IA] Tentando Claude (CLI local)...")
    resposta = _pedir_ao_claude(prompt)
    if resposta:
        print("[IA] ✨ Sucesso com: Claude")
        return sanitizar_resposta(resposta)

    for modelo in modelos_fallback if cliente else []:
        try:
            print(f"[IA] Tentando modelo: {modelo}...")
            response = cliente.models.generate_content(model=modelo, contents=prompt)
            print(f"[IA] ✨ Sucesso com: {modelo}")
            return sanitizar_resposta(response.text) + (
                "\n\n⚠️ Resposta do Gemini (reserva): código NÃO foi testado."
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            print(f"⚠️ {modelo} falhou: {exc}")

    return "Desculpe, o Claude e a cota gratuita de todos os modelos Gemini falharam. 🤖"
