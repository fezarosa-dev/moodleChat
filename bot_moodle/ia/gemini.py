"""Gemini (Google, tem cota gratuita): precisa de API_KEY.

Começa pelo modelo escolhido no menu e, se ele falhar (cota, sobrecarga, modelo sumido), desce a
lista MODELOS_GEMINI. A ferramenta testar_c roda sozinha (chamada automática de funções).
"""

from google import genai

from bot_moodle.ia import testador
from bot_moodle.inicio.preferencias import MODELOS_GEMINI, pref

MAX_RODADAS = 8           # máximo de testes que a IA pode pedir numa resposta


def criar_cliente(api_key: str) -> "genai.Client | None":
    """O cliente do Gemini; None sem chave (o Gemini falha e a linha segue para a próxima IA)."""
    return genai.Client(api_key=api_key) if api_key else None


def modelos_a_tentar(escolhido: str) -> list[str]:
    """O escolhido e os que vêm depois dele na lista (um fora da lista vai na frente de todos)."""
    if escolhido in MODELOS_GEMINI:
        return MODELOS_GEMINI[MODELOS_GEMINI.index(escolhido):]
    return [escolhido, *MODELOS_GEMINI]


def _configuracao(estado: dict):
    from google.genai import types  # pylint: disable=import-outside-toplevel

    def testar_c(codigo: str, entradas: list[str]) -> str:
        return testador.usar_ferramenta({"codigo": codigo, "entradas": entradas}, estado)

    testar_c.__doc__ = testador.testar_c.__doc__  # o Gemini lê a descrição da ferramenta daqui
    return types.GenerateContentConfig(
        system_instruction=testador.INSTRUCAO,
        tools=[testar_c],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(
            maximum_remote_calls=MAX_RODADAS),
    )


def _primeira_linha(exc: Exception) -> str:
    return str(exc).splitlines()[0][:150] if str(exc) else repr(exc)


def responder(cliente, prompt: str) -> tuple[str, dict]:
    """Tenta cada modelo até um responder. Lança erro se todos falharem."""
    if cliente is None:
        raise RuntimeError("API_KEY do Gemini não configurada no .env")
    estado = {"testou": False, "passou": False}
    config = _configuracao(estado)
    erro = "sem resposta"
    for modelo in modelos_a_tentar(pref("BOT_GEMINI_MODELO")):
        print(f"[IA] Gemini: tentando {modelo}...")
        try:
            texto = cliente.models.generate_content(model=modelo, contents=prompt, config=config).text
        except Exception as exc:  # pylint: disable=broad-exception-caught
            erro = _primeira_linha(exc)
            print(f"⚠️ {modelo} falhou: {erro}")
            continue
        if texto:
            estado["modelo"] = modelo
            return texto.strip(), estado
        # ponytail: sem texto (ex.: acabaram as rodadas de teste) conta como falha do modelo;
        # pedir a resposta final sem ferramentas resolveria se isso acontecer muito
        erro = "resposta vazia"
    raise RuntimeError(f"todos os modelos falharam (último erro: {erro})")
