"""Integração com IA: Claude Code (CLI), Claude API e Gemini, numa linha de reserva.

A ordem e os modelos vêm das preferências (BOT_*). Se a IA da vez falhar (erro, cota,
fora do ar, tempo esgotado), a próxima da linha tenta. Todas testam o código C antes
de responder: o Claude Code com as próprias ferramentas, as APIs com `testar_c`.
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from google import genai

from bot_moodle.preferencias import IAS, MODELOS_GEMINI, lista, pref

TIMEOUT_S = 300           # por pedido a uma IA
MAX_RODADAS = 8           # máximo de vezes que uma API testa e corrige numa resposta
EXEC_TIMEOUT_S = 10       # por execução do programa de teste
SAIDA_MAX = 2000          # caracteres de saída devolvidos à IA por execução


def criar_cliente(api_key: str) -> "genai.Client | None":
    """Cria o cliente Gemini. None sem chave."""
    return genai.Client(api_key=api_key) if api_key else None


# ── Ferramenta de teste (usada pelas APIs) ────────────────────────────────────

def _testar(codigo: str, entradas: list[str]) -> tuple[str, bool]:
    """Compila e roda o código; devolve (relatório para a IA, passou sem avisos nem erros)."""
    with tempfile.TemporaryDirectory(prefix="bot_moodle_", ignore_cleanup_errors=True) as pasta:
        fonte, prog = Path(pasta, "main.c"), str(Path(pasta, "prog"))
        fonte.write_text(codigo, encoding="utf-8")
        base = ["gcc", "-Wall", "-Wextra", "-g", "-o", prog, str(fonte), "-lm"]
        comp = None
        # com sanitizers primeiro; se não linkarem (ex.: Windows), sem eles
        for cmd in (base[:4] + ["-fsanitize=address,undefined"] + base[4:], base):
            comp = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=60, check=False)
            if comp.returncode == 0:
                break
        avisos = comp.stderr.strip()[:SAIDA_MAX]
        if comp.returncode != 0:
            return f"Compilação FALHOU:\n{avisos}", False
        partes = [f"Compilação ok{' com avisos:' if avisos else ''}\n{avisos}".strip()]
        passou = not avisos
        for i, entrada in enumerate(entradas or [""], 1):
            try:
                r = subprocess.run([prog], input=entrada, capture_output=True, text=True,
                                   encoding="utf-8", errors="replace",
                                   timeout=EXEC_TIMEOUT_S, check=False)
            except subprocess.TimeoutExpired:
                partes.append(f"Execução {i}: passou de {EXEC_TIMEOUT_S} s "
                              "(loop infinito ou esperando mais entrada)")
                passou = False
                continue
            saida = (r.stdout + r.stderr)[:SAIDA_MAX]
            partes.append(f"Execução {i} (código de saída {r.returncode}):\n{saida}")
            passou = passou and r.returncode == 0 and "runtime error" not in saida \
                and "Sanitizer" not in saida
        return "\n\n".join(partes), passou


def testar_c(codigo: str, entradas: list[str]) -> str:
    """Compila um programa C (gcc -Wall -Wextra, com AddressSanitizer e UBSan) e o executa
    uma vez para cada entrada, passada pelo stdin.

    Args:
        codigo: o programa C completo, com main.
        entradas: o texto do stdin de cada execução; use [""] se o programa não lê nada.

    Returns:
        Avisos ou erros do compilador e a saída de cada execução.
    """
    return _testar(codigo, entradas)[0]


def _usar_ferramenta(dados: dict, estado: dict) -> str:
    codigo = str(dados.get("codigo", ""))
    entradas = [str(e) for e in (dados.get("entradas") or [""])][:10]
    relatorio, passou = _testar(codigo, entradas)
    estado.update(testou=True, passou=passou)
    print(f"[IA] testou o código: {'passou' if passou else 'falhou'}")
    return relatorio


FERRAMENTA = {
    "name": "testar_c",
    "description": testar_c.__doc__,
    "input_schema": {
        "type": "object",
        "properties": {
            "codigo": {"type": "string", "description": "O programa C completo, com main."},
            "entradas": {"type": "array", "items": {"type": "string"},
                         "description": "O stdin de cada execução; [\"\"] se não lê nada."},
        },
        "required": ["codigo", "entradas"],
        "additionalProperties": False,
    },
}

_INSTRUCAO_API = (
    "Se a sua resposta contiver código C, você DEVE testá-lo antes de responder, com a "
    "ferramenta testar_c: passe o programa completo e entradas de teste, incluindo casos de "
    "borda. Corrija até compilar sem avisos e dar a saída esperada em todos os casos.\n"
    "A resposta final é só o texto para o aluno, seguindo as regras de formatação da mensagem."
)


# ── Claude Code (CLI) ─────────────────────────────────────────────────────────

# Usa a cota do plano logado na máquina. Roda como agente numa pasta temporária: escreve,
# compila e testa o código antes de responder.
_INSTRUCAO_CLI = (
    "Se a sua resposta contiver código C, você DEVE testá-lo antes de responder:\n"
    "1. Salve o código em main.c nesta pasta (Write).\n"
    "2. Compile: gcc -Wall -Wextra -g -fsanitize=address,undefined -o prog main.c -lm\n"
    "   (se os sanitizers não linkarem, compile sem -fsanitize).\n"
    "3. Rode com casos de teste, incluindo bordas: printf 'entrada\\n' | ./prog\n"
    "4. Corrija até compilar sem avisos e dar a saída esperada em todos os casos.\n"
    "Use UM comando simples por chamada do Bash (sem &&, ;, for, while, caminhos absolutos).\n"
    "A resposta final é só o texto para o aluno, seguindo as regras de formatação da mensagem."
)


def _comando_cli() -> list[str]:
    return [
        shutil.which("claude") or "claude", "-p",
        "--model", pref("BOT_CLI_MODELO"),
        "--effort", pref("BOT_CLI_EFFORT"),
        "--tools", "Bash,Write,Read,Edit",
        # Arquivos só dentro da pasta temporária; Bash só gcc, o binário e printf para entrada.
        # ponytail: ./prog executa código arbitrário (igual ao !run) e a distrobox compartilha
        # a home; isolar de verdade exigiria container sem home/rede.
        "--allowedTools",
        "Write(./**)", "Edit(./**)", "Read(./**)",
        "Bash(gcc *)", "Bash(./prog*)", "Bash(printf *)",
        "--setting-sources", "",     # ignora hooks/CLAUDE.md/config do usuário
        "--strict-mcp-config",       # sem servidores MCP
        "--no-session-persistence",  # não polui o histórico de sessões
        "--system-prompt", _INSTRUCAO_CLI,
    ]


def _claude_cli(_cliente, prompt: str) -> tuple[str, None]:
    """Roda `claude -p` com o prompt no stdin. Lança erro em qualquer falha."""
    try:
        # ignore_cleanup_errors: no Windows o prog.exe pode ainda estar travado ao apagar
        with tempfile.TemporaryDirectory(prefix="bot_moodle_", ignore_cleanup_errors=True) as pasta:
            proc = subprocess.run(
                _comando_cli(), input=prompt, capture_output=True, text=True,
                encoding="utf-8",  # Windows usaria cp1252 e quebraria os acentos
                errors="replace", timeout=TIMEOUT_S,
                cwd=pasta,  # área de trabalho isolada por pedido, longe de CLAUDE.md
                check=False,
            )
    except OSError as exc:
        dica = "instale o Claude Code e rode `claude` para fazer login"
        if os.name == "nt" and not shutil.which("git"):
            dica += "; ele precisa do Git for Windows (winget install Git.Git)"
        raise RuntimeError(f"Claude Code não encontrado ({exc}): {dica}") from exc
    saida = proc.stdout.strip()
    if proc.returncode != 0 or not saida:
        erro = (proc.stderr.strip() or saida).splitlines()
        raise RuntimeError(f"saiu com código {proc.returncode}: {erro[0] if erro else 'sem saída'}")
    return saida, None  # testa sozinho; o bot não sabe o resultado


# ── Claude API ────────────────────────────────────────────────────────────────

def _claude_api(_cliente, prompt: str) -> tuple[str, dict]:
    """Messages API com a ferramenta testar_c, num loop de até MAX_RODADAS testes."""
    import anthropic  # pylint: disable=import-outside-toplevel

    # sem ANTHROPIC_API_KEY o SDK ainda tenta o login do `ant auth login`
    cliente = anthropic.Anthropic(timeout=TIMEOUT_S, max_retries=1)
    estado = {"testou": False, "passou": False}
    mensagens = [{"role": "user", "content": prompt}]
    for rodada in range(MAX_RODADAS + 1):
        resp = cliente.messages.create(
            model=pref("BOT_API_MODELO"),
            max_tokens=16000,
            system=_INSTRUCAO_API,
            output_config={"effort": pref("BOT_API_EFFORT")},
            tools=[FERRAMENTA],
            # acabaram as rodadas: pede a resposta final sem testar de novo
            tool_choice={"type": "none" if rodada == MAX_RODADAS else "auto"},
            messages=mensagens,
        )
        if resp.stop_reason == "refusal":
            raise RuntimeError("a IA recusou o pedido")
        usos = [b for b in resp.content if b.type == "tool_use"]
        if not usos:
            return "".join(b.text for b in resp.content if b.type == "text").strip(), estado
        mensagens.append({"role": "assistant", "content": resp.content})
        mensagens.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": b.id, "content": _usar_ferramenta(b.input, estado)}
            for b in usos
        ]})
    raise RuntimeError("não respondeu depois dos testes")


# ── Gemini ────────────────────────────────────────────────────────────────────

def _gemini(cliente, prompt: str) -> tuple[str, dict]:
    """Tenta o modelo escolhido e desce a lista (cota, erro); a ferramenta roda sozinha."""
    from google.genai import types  # pylint: disable=import-outside-toplevel

    if cliente is None:
        raise RuntimeError("API_KEY do Gemini não configurada no .env")
    estado = {"testou": False, "passou": False}

    def testar_c_gemini(codigo: str, entradas: list[str]) -> str:
        return _usar_ferramenta({"codigo": codigo, "entradas": entradas}, estado)

    testar_c_gemini.__doc__ = testar_c.__doc__
    testar_c_gemini.__name__ = "testar_c"
    config = types.GenerateContentConfig(
        system_instruction=_INSTRUCAO_API,
        tools=[testar_c_gemini],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(
            maximum_remote_calls=MAX_RODADAS),
    )
    escolhido = pref("BOT_GEMINI_MODELO")
    modelos = (MODELOS_GEMINI[MODELOS_GEMINI.index(escolhido):]
               if escolhido in MODELOS_GEMINI else [escolhido, *MODELOS_GEMINI])
    erro = "sem resposta"
    for modelo in modelos:
        try:
            print(f"[IA] Gemini: tentando {modelo}...")
            texto = cliente.models.generate_content(model=modelo, contents=prompt, config=config).text
        except Exception as exc:  # pylint: disable=broad-exception-caught
            erro = str(exc).splitlines()[0][:150] if str(exc) else repr(exc)
            print(f"⚠️ {modelo} falhou: {erro}")
            continue
        if texto:
            estado["modelo"] = modelo
            return texto.strip(), estado
        # ponytail: sem texto (ex.: acabaram as rodadas de teste) conta como falha do modelo;
        # pedir a resposta final sem ferramentas resolveria se isso acontecer muito
        erro = "resposta vazia"
    raise RuntimeError(f"todos os modelos falharam (último erro: {erro})")


PROVEDORES = {"claude_cli": _claude_cli, "claude_api": _claude_api, "gemini": _gemini}


def chamar(nome: str, cliente, prompt: str):
    """Chama uma IA da linha. Lança erro se ela falhar."""
    return PROVEDORES[nome](cliente, prompt)


def _aviso(texto: str, estado: "dict | None") -> str:
    if estado is None:  # Claude Code testa sozinho
        return ""
    if estado["testou"] and not estado["passou"]:
        return "\n\n⚠️ O código não passou em todos os testes."
    if not estado["testou"] and ("#include" in texto or "main(" in texto):
        return "\n\n⚠️ O código NÃO foi testado."
    return ""


def pedir_a_ia(
    cliente: "genai.Client | None",
    pergunta: str,
    contexto_historico: str = "",
    modo_fix: bool = False,
) -> str:
    """
    Envia o prompt às IAs da linha de reserva, na ordem, até uma responder.

    Args:
        cliente: cliente do Gemini (None sem API_KEY).
        pergunta: texto da pergunta ou código a corrigir.
        contexto_historico: conversa anterior (perguntas, respostas e runs).
        modo_fix: se True, usa instrução de debugging em vez de tutoria.

    Returns:
        Resposta da IA, ou mensagem de falha.
    """
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

    # todas são tentadas a cada mensagem, mesmo as que falharam antes (podem ter voltado)
    for nome in lista("BOT_IAS"):
        if nome not in PROVEDORES:
            continue
        print(f"[IA] Tentando {IAS[nome]}...")
        try:
            texto, estado = chamar(nome, cliente, prompt)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            print(f"⚠️ {IAS[nome]} falhou: {exc}")
            continue
        if texto:
            print(f"[IA] ✨ Sucesso com: {IAS[nome]}")
            return texto + _aviso(texto, estado)
        print(f"⚠️ {IAS[nome]} respondeu vazio")

    return "Desculpe, todas as IAs da linha falharam (veja o terminal do bot). 🤖"
