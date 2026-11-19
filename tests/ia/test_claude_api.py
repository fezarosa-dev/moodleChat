"""Claude API: o loop de testes com a ferramenta testar_c (SDK falso, sem rede)."""

import shutil
from types import SimpleNamespace as NS

import anthropic
import pytest

from bot_moodle.ia import claude_api

CODIGO = '#include <stdio.h>\nint main(void){puts("oi");return 0;}'


def pede_teste(id_):
    return NS(stop_reason="tool_use", content=[
        NS(type="tool_use", id=id_, input={"codigo": CODIGO, "entradas": [""]})])


def responde(texto):
    return NS(stop_reason="end_turn", content=[NS(type="text", text=texto)])


@pytest.fixture(name="api")
def fixture_api(monkeypatch):
    """Troca o SDK por um falso que devolve as respostas da lista `api.respostas`, em ordem."""
    api = NS(respostas=[], pedidos=[])

    class AnthropicFalso:  # pylint: disable=too-few-public-methods
        def __init__(self, **_kwargs):
            self.messages = NS(create=lambda **kw: api.pedidos.append(kw) or api.respostas.pop(0))

    monkeypatch.setattr(anthropic, "Anthropic", AnthropicFalso)
    return api


def test_responde_direto_sem_testar(api):
    api.respostas = [responde("ponteiro guarda um endereço")]
    texto, estado = claude_api.responder(None, "o que é ponteiro?")
    assert texto == "ponteiro guarda um endereço"
    assert estado == {"testou": False, "passou": False}


@pytest.mark.skipif(not shutil.which("gcc"), reason="precisa de gcc")
def test_executa_o_teste_pedido_e_devolve_o_resultado(api):
    api.respostas = [pede_teste("t1"), responde("pronto")]
    texto, estado = claude_api.responder(None, "faz um oi")
    assert texto == "pronto" and estado == {"testou": True, "passou": True}
    resultado = api.pedidos[1]["messages"][-1]["content"][0]
    assert resultado["tool_use_id"] == "t1" and "oi" in resultado["content"]


def test_usa_modelo_e_effort_do_menu(api, monkeypatch):
    monkeypatch.setenv("BOT_API_MODELO", "claude-opus-5-5")
    monkeypatch.setenv("BOT_API_EFFORT", "high")
    api.respostas = [responde("ok")]
    claude_api.responder(None, "oi")
    assert api.pedidos[0]["model"] == "claude-opus-5-5"
    assert api.pedidos[0]["output_config"] == {"effort": "high"}


def test_na_ultima_rodada_proibe_novos_testes(api, monkeypatch):
    monkeypatch.setattr(claude_api, "MAX_RODADAS", 1)
    monkeypatch.setattr(claude_api.testador, "usar_ferramenta", lambda _d, _e: "ok")
    api.respostas = [pede_teste("t1"), responde("final")]
    assert claude_api.responder(None, "oi")[0] == "final"
    assert [p["tool_choice"]["type"] for p in api.pedidos] == ["auto", "none"]


def test_recusa_vira_erro_para_a_linha_passar_adiante(api):
    api.respostas = [NS(stop_reason="refusal", content=[])]
    with pytest.raises(RuntimeError, match="recusou"):
        claude_api.responder(None, "oi")
