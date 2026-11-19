"""O testador de código C que as IAs usam antes de responder.

A Claude API e o Gemini recebem a ferramenta `testar_c`: compila com gcc -Wall -Wextra (e com
AddressSanitizer/UBSan quando o sistema permite) e roda o programa com as entradas que a IA
escolher. O Claude Code testa sozinho, com as próprias ferramentas (veja claude_cli.py).
"""

import subprocess
import tempfile
from pathlib import Path

EXEC_TIMEOUT_S = 10       # por execução do programa de teste
SAIDA_MAX = 2000          # caracteres de saída devolvidos à IA por execução
MAX_ENTRADAS = 10         # casos de teste por chamada
SANITIZERS = ["-fsanitize=address,undefined"]
# o que os sanitizers escrevem quando acham um erro em tempo de execução
SINAIS_DE_ERRO = ("runtime error", "Sanitizer")

INSTRUCAO = (
    "Se a sua resposta contiver código C, você DEVE testá-lo antes de responder, com a "
    "ferramenta testar_c: passe o programa completo e entradas de teste, incluindo casos de "
    "borda. Corrija até compilar sem avisos e dar a saída esperada em todos os casos.\n"
    "A resposta final é só o texto para o aluno, seguindo as regras de formatação da mensagem."
)


def _compilar(fonte: Path, programa: str) -> subprocess.CompletedProcess:
    """Compila com sanitizers; se eles não linkarem (ex.: MinGW no Windows), compila sem."""
    base = ["gcc", "-Wall", "-Wextra", "-g", "-o", programa, str(fonte), "-lm"]
    resultado = None
    for comando in (base[:4] + SANITIZERS + base[4:], base):
        resultado = subprocess.run(comando, capture_output=True, text=True, encoding="utf-8",
                                   errors="replace", timeout=60, check=False)
        if resultado.returncode == 0:
            break
    return resultado


def _executar(programa: str, numero: int, entrada: str) -> tuple[str, bool]:
    """Roda uma vez com a entrada no stdin; devolve (relatório, passou)."""
    try:
        r = subprocess.run([programa], input=entrada, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=EXEC_TIMEOUT_S, check=False)
    except subprocess.TimeoutExpired:
        return (f"Execução {numero}: passou de {EXEC_TIMEOUT_S} s "
                "(loop infinito ou esperando mais entrada)"), False
    saida = (r.stdout + r.stderr)[:SAIDA_MAX]
    passou = r.returncode == 0 and not any(sinal in saida for sinal in SINAIS_DE_ERRO)
    return f"Execução {numero} (código de saída {r.returncode}):\n{saida}", passou


def testar(codigo: str, entradas: list[str]) -> tuple[str, bool]:
    """Compila e roda o código; devolve (relatório para a IA, passou sem avisos nem erros)."""
    # ignore_cleanup_errors: no Windows o prog.exe pode ainda estar travado ao apagar
    with tempfile.TemporaryDirectory(prefix="bot_moodle_", ignore_cleanup_errors=True) as pasta:
        fonte, programa = Path(pasta, "main.c"), str(Path(pasta, "prog"))
        fonte.write_text(codigo, encoding="utf-8")
        compilacao = _compilar(fonte, programa)
        avisos = compilacao.stderr.strip()[:SAIDA_MAX]
        if compilacao.returncode != 0:
            return f"Compilação FALHOU:\n{avisos}", False
        execucoes = [_executar(programa, i, entrada) for i, entrada in enumerate(entradas or [""], 1)]
    cabecalho = f"Compilação ok{' com avisos:' if avisos else ''}\n{avisos}".strip()
    relatorio = "\n\n".join([cabecalho] + [texto for texto, _ in execucoes])
    return relatorio, not avisos and all(passou for _, passou in execucoes)


def testar_c(codigo: str, entradas: list[str]) -> str:
    """Compila um programa C (gcc -Wall -Wextra, com AddressSanitizer e UBSan) e o executa
    uma vez para cada entrada, passada pelo stdin.

    Args:
        codigo: o programa C completo, com main.
        entradas: o texto do stdin de cada execução; use [""] se o programa não lê nada.

    Returns:
        Avisos ou erros do compilador e a saída de cada execução.
    """
    return testar(codigo, entradas)[0]


def usar_ferramenta(dados: dict, estado: dict) -> str:
    """Executa um pedido de teste da IA e anota em `estado` se testou e se passou."""
    codigo = str(dados.get("codigo", ""))
    entradas = [str(e) for e in (dados.get("entradas") or [""])][:MAX_ENTRADAS]
    relatorio, passou = testar(codigo, entradas)
    estado.update(testou=True, passou=passou)
    print(f"[IA] testou o código: {'passou' if passou else 'falhou'}")
    return relatorio


# a ferramenta no formato da Messages API (a Claude API a recebe assim)
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
