"""Gemini: descer a lista de modelos quando um falha (cliente falso, sem rede)."""

from types import SimpleNamespace as NS

import pytest

from bot_moodle.ia import gemini
from bot_moodle.inicio.preferencias import MODELOS_GEMINI


def cliente_falso(respostas: dict):
    """Cliente que, para cada modelo, devolve o texto de `respostas` ou levanta a exceção dele."""
    tentados = []

    def generate_content(model, **_kwargs):
        tentados.append(model)
        resposta = respostas.get(model, RuntimeError("404 NOT_FOUND"))
        if isinstance(resposta, Exception):
            raise resposta
        return NS(text=resposta)

    return NS(models=NS(generate_content=generate_content)), tentados


def test_sem_chave_falha_para_a_linha_seguir():
    with pytest.raises(RuntimeError, match="API_KEY"):
        gemini.responder(None, "oi")


def test_sem_chave_nao_cria_cliente():
    assert gemini.criar_cliente("") is None


def test_responde_com_o_modelo_escolhido(monkeypatch):
    monkeypatch.setenv("BOT_GEMINI_MODELO", "gemini-2.5-flash")
    cliente, tentados = cliente_falso({"gemini-2.5-flash": " oi "})
    texto, estado = gemini.responder(cliente, "oi")
    assert texto == "oi" and estado["modelo"] == "gemini-2.5-flash" and tentados == ["gemini-2.5-flash"]


def test_desce_a_lista_quando_um_modelo_falha(monkeypatch):
    primeiro, segundo = MODELOS_GEMINI[0], MODELOS_GEMINI[1]
    monkeypatch.setenv("BOT_GEMINI_MODELO", primeiro)
    cliente, tentados = cliente_falso({primeiro: RuntimeError("503 UNAVAILABLE"), segundo: "ok"})
    assert gemini.responder(cliente, "oi")[1]["modelo"] == segundo
    assert tentados == [primeiro, segundo]


def test_resposta_vazia_tenta_o_proximo_modelo(monkeypatch):
    primeiro, segundo = MODELOS_GEMINI[0], MODELOS_GEMINI[1]
    monkeypatch.setenv("BOT_GEMINI_MODELO", primeiro)
    cliente, _ = cliente_falso({primeiro: "", segundo: "ok"})
    assert gemini.responder(cliente, "oi")[0] == "ok"


def test_todos_falhando_mostra_o_ultimo_erro(monkeypatch):
    monkeypatch.setenv("BOT_GEMINI_MODELO", MODELOS_GEMINI[-1])
    cliente, _ = cliente_falso({MODELOS_GEMINI[-1]: RuntimeError("429 cota\ndetalhes")})
    with pytest.raises(RuntimeError, match="último erro: 429 cota"):
        gemini.responder(cliente, "oi")


def test_ordem_dos_modelos_a_partir_do_escolhido():
    assert gemini.modelos_a_tentar(MODELOS_GEMINI[2]) == MODELOS_GEMINI[2:]
    assert gemini.modelos_a_tentar("gemini-novo") == ["gemini-novo", *MODELOS_GEMINI]
