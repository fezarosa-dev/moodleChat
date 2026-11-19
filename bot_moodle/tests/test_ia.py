"""Linha de reserva das IAs, ferramenta testar_c, preferências e vigia (sem rede)."""

import subprocess
import sys

import pytest

from bot_moodle import preferencias, vigia
from bot_moodle.core import ai


def test_linha_de_reserva(monkeypatch):
    chamadas = []

    def falha(_c, _p):
        chamadas.append("cli")
        raise RuntimeError("cota estourada")

    def responde(_c, _p):
        chamadas.append("api")
        return "#include <stdio.h>\nint main(void){}", {"testou": True, "passou": False}

    monkeypatch.setitem(ai.PROVEDORES, "claude_cli", falha)
    monkeypatch.setitem(ai.PROVEDORES, "claude_api", responde)
    monkeypatch.setenv("BOT_IAS", "claude_cli,claude_api,gemini")
    resp = ai.pedir_a_ia(None, "oi")
    assert chamadas == ["cli", "api"]  # a que falhou é tentada, a próxima responde
    assert resp.endswith("não passou em todos os testes.")
    resp = ai.pedir_a_ia(None, "oi")
    assert chamadas == ["cli", "api", "cli", "api"]  # tenta de novo a cada mensagem

    monkeypatch.setitem(ai.PROVEDORES, "claude_api", falha)
    monkeypatch.setitem(ai.PROVEDORES, "gemini", falha)
    assert "todas as IAs da linha falharam" in ai.pedir_a_ia(None, "oi")


def test_aviso_sem_teste():
    assert ai._aviso("int main(void){}", {"testou": False, "passou": False})  # pylint: disable=protected-access
    assert ai._aviso("só texto", {"testou": False, "passou": False}) == ""  # pylint: disable=protected-access
    assert ai._aviso("int main(void){}", None) == ""  # pylint: disable=protected-access


def test_testar_c():
    ok = '#include <stdio.h>\nint main(void){int n; scanf("%d",&n); printf("%d\\n", n*2); return 0;}'
    relatorio, passou = ai._testar(ok, ["21\n"])  # pylint: disable=protected-access
    assert passou and "42" in relatorio
    _, passou = ai._testar("int main(void){ return 1 }", [""])  # pylint: disable=protected-access
    assert not passou  # não compila
    estouro = "int main(void){int v[2]; volatile int i=5; v[i]=1; return v[0];}"
    _, passou = ai._testar(estouro, [""])  # pylint: disable=protected-access
    assert not passou  # sanitizer pega


def test_salvar_preferencias(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# comentário\nAPI_KEY=x\nBOT_IAS=gemini\n")
    preferencias.salvar({"BOT_IAS": "claude_api,gemini", "BOT_VIGIA": "0"}, env)
    assert env.read_text() == "# comentário\nAPI_KEY=x\nBOT_IAS=claude_api,gemini\nBOT_VIGIA=0\n"


def test_vigia_reinicia_ou_desiste():
    def filho(codigo):
        return subprocess.Popen([sys.executable, "-c", f"raise SystemExit({codigo})"])

    assert vigia.vigiar(filho(1), False, 0) == "o bot caiu (código 1)"
    with pytest.raises(KeyboardInterrupt):  # Flask saindo normal após Ctrl+C (Windows)
        vigia.vigiar(filho(0), False, 0)
    with pytest.raises(SystemExit):
        vigia.vigiar(filho(vigia.NAO_REINICIAR), False, 0)


def test_claude_api_loop(monkeypatch):
    import anthropic  # pylint: disable=import-outside-toplevel
    from types import SimpleNamespace as NS  # pylint: disable=import-outside-toplevel

    codigo = '#include <stdio.h>\nint main(void){puts("oi");return 0;}'
    respostas = [
        NS(stop_reason="tool_use", content=[
            NS(type="tool_use", id="t1", input={"codigo": codigo, "entradas": [""]})]),
        NS(stop_reason="end_turn", content=[NS(type="text", text="pronto")]),
    ]
    pedidos = []

    class Falso:  # pylint: disable=missing-class-docstring,too-few-public-methods
        def __init__(self, **_kw):
            self.messages = NS(create=lambda **kw: pedidos.append(kw) or respostas.pop(0))

    monkeypatch.setattr(anthropic, "Anthropic", Falso)
    texto, estado = ai._claude_api(None, "faz um oi")  # pylint: disable=protected-access
    assert texto == "pronto" and estado == {"testou": True, "passou": True}
    resultado = pedidos[1]["messages"][-1]["content"][0]
    assert resultado["tool_use_id"] == "t1" and "oi" in resultado["content"]
    assert pedidos[0]["output_config"] == {"effort": "medium"}


def test_vigia_limpa_vida_velha(monkeypatch, tmp_path):
    """Arquivo de vida de uma execução anterior (ou de plataforma desligada) faria o vigia
    achar que o bot travou e reiniciar em loop."""
    monkeypatch.chdir(tmp_path)
    for vida in vigia.VIDAS.values():
        vida.touch()

    def popen(*_a, **_k):
        assert not any(v.exists() for v in vigia.VIDAS.values())
        raise KeyboardInterrupt

    monkeypatch.setattr(vigia.subprocess, "Popen", popen)
    vigia.rodar(servidor=False)  # o KeyboardInterrupt vira "Parando o bot..."
