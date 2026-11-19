"""O ponto de entrada: o que sobe conforme as preferências e a reserva entre os jeitos de conectar."""

import threading
import time

import pytest

from bot_moodle import app as app_module
from bot_moodle.inicio import vigia


def leitor_que_dura(segundos: float) -> threading.Thread:
    """Uma thread que finge ler mensagens por um tempo e depois para."""
    leitor = threading.Thread(target=time.sleep, args=(segundos,), daemon=True)
    leitor.start()
    return leitor


@pytest.fixture(name="app")
def fixture_app(pasta_isolada, ambiente_limpo):  # pylint: disable=unused-argument
    return app_module.create_app()


# ── escolhas ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("plataformas, modos, instagram, moodle", [
    ("moodle,instagram", "api,extensao", True, ("api", "extensao")),
    ("moodle", "extensao", False, ("extensao",)),
    ("instagram", "api", True, ()),
    ("moodle", "extensao,api", False, ("extensao", "api")),
])
def test_escolhas_vem_das_preferencias(monkeypatch, plataformas, modos, instagram, moodle):
    monkeypatch.setenv("BOT_PLATAFORMAS", plataformas)
    monkeypatch.setenv("BOT_MOODLE_MODOS", modos)
    escolhas = app_module.Escolhas.das_preferencias()
    assert (escolhas.instagram, escolhas.moodle) == (instagram, moodle)


def test_servidor_so_quando_a_extensao_esta_na_sequencia(monkeypatch):
    monkeypatch.setenv("BOT_MOODLE_MODOS", "api")
    assert not app_module.Escolhas.das_preferencias().pode_ter_servidor
    monkeypatch.setenv("BOT_MOODLE_MODOS", "api,extensao")
    assert app_module.Escolhas.das_preferencias().pode_ter_servidor


# ── o app ────────────────────────────────────────────────────────────────────

def test_app_tem_a_rota_dos_comandos_e_a_de_saude(app):
    cliente = app.test_client()
    assert cliente.get("/health").data == b"ok"
    resposta = cliente.post("/check_and_save", json={"id": "1", "texto": "oi"}).json
    assert resposta == {"status": "new", "is_command": False}


def test_o_banco_fica_em_dados(app):  # pylint: disable=unused-argument
    assert (app_module.caminhos.BANCO).exists()


# ── reserva entre os jeitos de conectar ──────────────────────────────────────

def test_se_o_primeiro_jeito_nao_sobe_usa_a_reserva(app):
    usados = []
    plataforma = app_module.Plataforma("Moodle", [
        ("api", lambda _app: usados.append("api")),  # sem chave: não sobe
        ("extensao", lambda _app: usados.append("extensao") or leitor_que_dura(5)),
    ])
    plataforma.subir(app)
    assert usados == ["api", "extensao"] and plataforma.atual == "extensao" and plataforma.viva()


def test_o_primeiro_que_sobe_e_o_usado(app):
    plataforma = app_module.Plataforma("Moodle", [
        ("api", lambda _app: leitor_que_dura(5)),
        ("extensao", lambda _app: pytest.fail("a reserva não devia subir")),
    ])
    plataforma.subir(app)
    assert plataforma.atual == "api"


def test_se_o_jeito_atual_para_a_reserva_assume(app):
    plataforma = app_module.Plataforma("Moodle", [
        ("api", lambda _app: leitor_que_dura(0.1)),  # ex.: a chave venceu no meio do uso
        ("extensao", lambda _app: leitor_que_dura(5)),
    ])
    plataforma.subir(app)
    plataforma.leitor.join()
    plataforma.subir(app)
    assert plataforma.atual == "extensao" and plataforma.viva()


def test_sem_reserva_sobrando_a_plataforma_acabou(app):
    plataforma = app_module.Plataforma("Moodle", [("api", lambda _app: None)])
    plataforma.subir(app)
    assert plataforma.acabou()


def test_quando_todas_acabam_sai_sem_reiniciar(app):
    plataforma = app_module.Plataforma("Instagram", [("login", lambda _app: leitor_que_dura(0.1))])
    with pytest.raises(SystemExit) as saida:
        app_module._manter(app, [plataforma])  # pylint: disable=protected-access
    assert saida.value.code == vigia.NAO_REINICIAR


def test_plataformas_ligadas_conforme_as_escolhas():
    escolhas = app_module.Escolhas(instagram=True, moodle=("extensao", "api"), vigia=False)
    ligadas = app_module.plataformas(escolhas)
    assert [p.nome for p in ligadas] == ["Moodle", "Instagram"]
    assert [jeito for jeito, _ in ligadas[0].jeitos] == ["extensao", "api"]


# ── main ─────────────────────────────────────────────────────────────────────

def test_com_vigia_ligado_o_main_entrega_para_o_vigia(monkeypatch):
    monkeypatch.setenv("BOT_VIGIA", "1")
    monkeypatch.setenv("BOT_PLATAFORMAS", "moodle")
    monkeypatch.setenv("BOT_MOODLE_MODOS", "api,extensao")
    chamadas = []
    # lambda e não chamadas.append: o main chama rodar(servidor=...) pelo nome
    monkeypatch.setattr(vigia, "rodar", lambda servidor: chamadas.append(servidor))  # pylint: disable=unnecessary-lambda
    app_module.main()
    assert chamadas == [True]  # a extensão pode subir como reserva: o vigia confere o servidor


def test_vigiado_o_main_sobe_as_plataformas(monkeypatch):
    monkeypatch.setenv("BOT_VIGIADO", "1")
    monkeypatch.setenv("BOT_PLATAFORMAS", "moodle")
    monkeypatch.setenv("BOT_MOODLE_MODOS", "api")
    monkeypatch.setitem(app_module.INICIAR_MOODLE, "api", lambda _app: None)  # sem chave
    with pytest.raises(SystemExit) as saida:
        app_module.main()
    assert saida.value.code == vigia.NAO_REINICIAR
