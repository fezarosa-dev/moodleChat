"""A linha de reserva das IAs: monta o prompt e tenta cada IA, na ordem do menu, até uma responder.

A ordem vem de BOT_IAS. Se a IA da vez falhar (erro, cota, fora do ar, tempo esgotado), a próxima
tenta. Todas são tentadas de novo a cada mensagem, mesmo as que falharam antes (podem ter voltado).
"""

from bot_moodle.ia import claude_api, claude_cli, gemini
from bot_moodle.inicio.preferencias import IAS, lista

# cada IA recebe (cliente do Gemini, prompt) e devolve (texto, estado dos testes ou None)
PROVEDORES = {
    "claude_cli": claude_cli.responder,
    "claude_api": claude_api.responder,
    "gemini": gemini.responder,
}

CABECALHO = "Você é um tutor acadêmico de programação especializado em Ciência da Computação."
INSTRUCOES = {
    False: ("Você é um tutor acadêmico de programação. "
            "Forneça explicações diretas caso solicitado e, "
            "caso não tenha sido solicitada explicação, forneça apenas a resposta direta."),
    True: ("Você é um especialista em debugging e correção de código. "
           "Identifique o erro de sintaxe ou lógica, corrija o código "
           "e forneça a resposta de forma extremamente direta."),
}
FORMATACAO = (
    "REGRA CRÍTICA DE FORMATAÇÃO:\n"
    "Responda APENAS em texto puro (Plain Text). NÃO use nenhuma formatação Markdown (.md).\n"
    "NÃO use asteriscos para negrito (**), NÃO use blocos de código com crases (```c) e NÃO use #.\n"
    "Se houver código em C, apenas pule uma linha e escreva o código "
    "diretamente com identação normal."
)
TODAS_FALHARAM = "Desculpe, todas as IAs da linha falharam (veja o terminal do bot). 🤖"


def montar_prompt(pergunta: str, contexto: str = "", modo_fix: bool = False) -> str:
    """O texto enviado à IA: papel, regras de formatação, conversa anterior e a pergunta."""
    partes = [f"{CABECALHO}\n{INSTRUCOES[modo_fix]}", FORMATACAO]
    if contexto:
        partes.append(f"CONVERSA ATÉ AQUI (mais antiga primeiro; use como contexto):\n"
                      f"{contexto}\n---------")
    partes.append(f"SOLICITAÇÃO ATUAL: {pergunta}")
    return "\n\n".join(partes)


def aviso(texto: str, estado: "dict | None") -> str:
    """O aviso que vai no fim da resposta quando o código não passou ou não foi testado."""
    if estado is None:  # Claude Code testa sozinho
        return ""
    if estado["testou"] and not estado["passou"]:
        return "\n\n⚠️ O código não passou em todos os testes."
    tem_codigo = "#include" in texto or "main(" in texto
    if not estado["testou"] and tem_codigo:
        return "\n\n⚠️ O código NÃO foi testado."
    return ""


def chamar(nome: str, cliente, prompt: str):
    """Chama uma IA da linha. Lança erro se ela falhar."""
    return PROVEDORES[nome](cliente, prompt)


def _tentar(nome: str, cliente, prompt: str) -> "str | None":
    """A resposta (com o aviso dos testes) de uma IA, ou None se ela falhar."""
    print(f"[IA] Tentando {IAS[nome]}...")
    try:
        texto, estado = chamar(nome, cliente, prompt)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"⚠️ {IAS[nome]} falhou: {exc}")
        return None
    if not texto:
        print(f"⚠️ {IAS[nome]} respondeu vazio")
        return None
    print(f"[IA] ✨ Sucesso com: {IAS[nome]}")
    return texto + aviso(texto, estado)


def pedir_a_ia(cliente, pergunta: str, contexto_historico: str = "", modo_fix: bool = False) -> str:
    """Envia a pergunta às IAs da linha, na ordem, até uma responder.

    Args:
        cliente: cliente do Gemini (None sem API_KEY).
        pergunta: texto da pergunta ou código a corrigir.
        contexto_historico: conversa anterior (perguntas, respostas e runs).
        modo_fix: True usa a instrução de correção de bugs em vez da de tutoria.
    """
    prompt = montar_prompt(pergunta, contexto_historico, modo_fix)
    for nome in lista("BOT_IAS"):
        resposta = _tentar(nome, cliente, prompt) if nome in PROVEDORES else None
        if resposta:
            return resposta
    return TODAS_FALHARAM
