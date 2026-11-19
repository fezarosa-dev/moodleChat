"""Claude Code (CLI): usa a cota do plano do Claude logado na máquina, sem API key.

Roda `claude -p` como agente numa pasta temporária: ele escreve, compila e testa o código
sozinho antes de responder.
"""

import os
import shutil
import subprocess
import tempfile

from bot_moodle.inicio.preferencias import pref

TIMEOUT_S = 300

INSTRUCAO = (
    "Se a sua resposta contiver código C, você DEVE testá-lo antes de responder:\n"
    "1. Salve o código em main.c nesta pasta (Write).\n"
    "2. Compile: gcc -Wall -Wextra -g -fsanitize=address,undefined -o prog main.c -lm\n"
    "   (se os sanitizers não linkarem, compile sem -fsanitize).\n"
    "3. Rode com casos de teste, incluindo bordas: printf 'entrada\\n' | ./prog\n"
    "4. Corrija até compilar sem avisos e dar a saída esperada em todos os casos.\n"
    "Use UM comando simples por chamada do Bash (sem &&, ;, for, while, caminhos absolutos).\n"
    "A resposta final é só o texto para o aluno, seguindo as regras de formatação da mensagem."
)


def comando() -> list[str]:
    """A linha de comando do `claude`, com o modelo e o effort das preferências."""
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
        "--system-prompt", INSTRUCAO,
    ]


def _dica_de_instalacao() -> str:
    dica = "instale o Claude Code e rode `claude` para fazer login"
    if os.name == "nt" and not shutil.which("git"):
        dica += "; ele precisa do Git for Windows (winget install Git.Git)"
    return dica


def responder(_cliente, prompt: str) -> tuple[str, None]:
    """Roda `claude -p` com o prompt no stdin. Lança RuntimeError em qualquer falha."""
    try:
        # ignore_cleanup_errors: no Windows o prog.exe pode ainda estar travado ao apagar
        with tempfile.TemporaryDirectory(prefix="bot_moodle_", ignore_cleanup_errors=True) as pasta:
            proc = subprocess.run(
                comando(), input=prompt, capture_output=True, text=True,
                encoding="utf-8",  # o Windows usaria cp1252 e quebraria os acentos
                errors="replace", timeout=TIMEOUT_S,
                cwd=pasta,  # área de trabalho isolada por pedido, longe de CLAUDE.md
                check=False,
            )
    except OSError as exc:
        raise RuntimeError(f"Claude Code não encontrado ({exc}): {_dica_de_instalacao()}") from exc
    saida = proc.stdout.strip()
    if proc.returncode == 0 and saida:
        return saida, None  # testa sozinho: o bot não sabe o resultado dos testes
    erro = (proc.stderr.strip() or saida).splitlines()
    raise RuntimeError(f"saiu com código {proc.returncode}: {erro[0] if erro else 'sem saída'}")
