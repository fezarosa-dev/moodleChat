"""O servidor do modo extensão: sobe numa thread na porta e não sobe se ela estiver ocupada."""

import socket
import urllib.request

from flask import Flask

from bot_moodle.plataformas import extensao


def porta_livre() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_sobe_e_responde_na_porta(monkeypatch):
    numero = porta_livre()
    monkeypatch.setenv("PORT", str(numero))
    app = Flask(__name__)
    app.add_url_rule("/health", "health", lambda: "ok")
    assert extensao.iniciar(app).is_alive()
    with urllib.request.urlopen(f"http://127.0.0.1:{numero}/health", timeout=5) as resposta:
        assert resposta.read() == b"ok"


def test_porta_ocupada_nao_sobe_para_a_reserva_assumir(monkeypatch, capsys):
    with socket.create_server(("127.0.0.1", 0)) as ocupada:
        monkeypatch.setenv("PORT", str(ocupada.getsockname()[1]))
        assert extensao.iniciar(Flask(__name__)) is None
    assert "está ocupada" in capsys.readouterr().out


def test_porta_padrao_e_5000():
    assert extensao.porta() == 5000
