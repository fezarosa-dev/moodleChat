"""Claude API (Messages API, paga por uso): precisa de ANTHROPIC_API_KEY.

Recebe a ferramenta testar_c e roda num loop: a cada pedido de teste, o bot executa o código e
devolve o resultado, até a IA responder (no máximo MAX_RODADAS testes).
"""

from bot_moodle.ia import testador
from bot_moodle.inicio.preferencias import pref

TIMEOUT_S = 300
MAX_RODADAS = 8           # máximo de vezes que a IA testa e corrige numa resposta
MAX_TOKENS = 16000


def _resultados_dos_testes(usos: list, estado: dict) -> dict:
    """A mensagem com o resultado de cada teste pedido pela IA."""
    return {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": uso.id,
         "content": testador.usar_ferramenta(uso.input, estado)}
        for uso in usos
    ]}


def responder(_cliente, prompt: str) -> tuple[str, dict]:
    """Pede a resposta, executando os testes que a IA pedir. Lança erro se ela falhar."""
    import anthropic  # pylint: disable=import-outside-toplevel

    # sem ANTHROPIC_API_KEY o SDK ainda tenta o login do `ant auth login`
    cliente = anthropic.Anthropic(timeout=TIMEOUT_S, max_retries=1)
    estado = {"testou": False, "passou": False}
    mensagens = [{"role": "user", "content": prompt}]
    for rodada in range(MAX_RODADAS + 1):
        ultima_rodada = rodada == MAX_RODADAS
        resposta = cliente.messages.create(
            model=pref("BOT_API_MODELO"),
            max_tokens=MAX_TOKENS,
            system=testador.INSTRUCAO,
            output_config={"effort": pref("BOT_API_EFFORT")},
            tools=[testador.FERRAMENTA],
            # acabaram as rodadas: pede a resposta final sem testar de novo
            tool_choice={"type": "none" if ultima_rodada else "auto"},
            messages=mensagens,
        )
        if resposta.stop_reason == "refusal":
            raise RuntimeError("a IA recusou o pedido")
        usos = [bloco for bloco in resposta.content if bloco.type == "tool_use"]
        if not usos:
            texto = "".join(bloco.text for bloco in resposta.content if bloco.type == "text")
            return texto.strip(), estado
        mensagens.append({"role": "assistant", "content": resposta.content})
        mensagens.append(_resultados_dos_testes(usos, estado))
    raise RuntimeError("não respondeu depois dos testes")
