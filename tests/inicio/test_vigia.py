"""O vigia: reinicia o bot que caiu ou travou, para no Ctrl+C e desiste se reiniciar demais."""

import os
import subprocess
import sys
import time
import urllib.request

import pytest

from bot_moodle.inicio import vigia


@pytest.fixture(name="rapido", autouse=True)
def fixture_rapido(monkeypatch, tmp_path):
    """Tempos curtos e arquivos de vida numa pasta temporária."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(vigia, "PING_S", 0.2)
    monkeypatch.setattr(vigia, "CARENCIA_S", 0)


POPEN = subprocess.Popen  # o original: alguns testes trocam o subprocess.Popen do vigia


def filho_que_sai(codigo):
    return POPEN([sys.executable, "-c", f"raise SystemExit({codigo})"])


def filho_que_fica(segundos=60):
    # sai com 1 (e não 0) se ninguém o parar: 0 seria lido como Ctrl+C
    return POPEN([sys.executable, "-c", f"import time; time.sleep({segundos}); raise SystemExit(1)"])


def test_bot_que_caiu_e_reiniciado():
    assert vigia.vigiar(filho_que_sai(1), False, 0) == "o bot caiu (código 1)"


@pytest.mark.parametrize("codigo", [0, 130])  # 0: o Flask sai normal depois do Ctrl+C (Windows)
def test_ctrl_c_no_bot_para_o_vigia_tambem(codigo):
    with pytest.raises(KeyboardInterrupt):
        vigia.vigiar(filho_que_sai(codigo), False, 0)


def test_erro_que_reiniciar_nao_resolve_para_tudo():
    with pytest.raises(SystemExit):
        vigia.vigiar(filho_que_sai(vigia.NAO_REINICIAR), False, 0)


def servidor_falso(monkeypatch, respostas: list):
    """/health responde conforme a lista (True = ok); acabou a lista, não responde mais."""
    class Resposta:  # pylint: disable=too-few-public-methods
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    def urlopen(*_args, **_kwargs):
        if respostas and respostas.pop(0):
            return Resposta()
        raise OSError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)


def test_servidor_que_parou_de_responder_e_reiniciado(monkeypatch):
    servidor_falso(monkeypatch, [True])  # respondeu uma vez e travou
    filho = filho_que_fica()
    assert "o servidor não responde" in vigia.vigiar(filho, True, 5000)
    assert filho.poll() is not None  # o vigia parou o processo travado


def test_servidor_que_nunca_subiu_nao_conta_como_travado(monkeypatch):
    """Com a reserva (API primeiro), o servidor da extensão pode nem subir: isso não é travar."""
    servidor_falso(monkeypatch, [])
    assert vigia.vigiar(filho_que_fica(2), True, 5000) == "o bot caiu (código 1)"


def test_plataforma_que_parou_de_ler_e_reiniciada(monkeypatch):
    monkeypatch.setattr(vigia, "PARADO_S", 1)
    vida = next(iter(vigia.VIDAS.values()))
    vida.parent.mkdir(exist_ok=True)
    vida.touch()
    antigo = time.time() - 10
    os.utime(vida, (antigo, antigo))
    filho = filho_que_fica()
    assert "parou de ler as mensagens" in vigia.vigiar(filho, False, 0)
    assert filho.poll() is not None


def test_arquivo_de_vida_velho_e_apagado_antes_de_subir(monkeypatch):
    """Um arquivo de vida de uma execução anterior (ou de plataforma desligada) faria o vigia
    achar que o bot travou e reiniciar em loop."""
    for vida in vigia.VIDAS.values():
        vida.parent.mkdir(exist_ok=True)
        vida.touch()

    def popen(*_args, **_kwargs):
        assert not any(vida.exists() for vida in vigia.VIDAS.values())
        raise KeyboardInterrupt

    monkeypatch.setattr(vigia.subprocess, "Popen", popen)
    vigia.rodar(servidor=False)  # o KeyboardInterrupt vira "Parando o bot..."


def test_desiste_depois_de_reiniciar_demais(monkeypatch):
    monkeypatch.setattr(vigia.subprocess, "Popen", lambda *_a, **_k: filho_que_sai(1))
    with pytest.raises(SystemExit, match="desistindo"):
        vigia.rodar(servidor=False)
