"""Conversa contínua: !chat/!fix/!run entram no contexto e o !chclear zera tudo."""

from flask import Flask

from bot_moodle import db
from bot_moodle.core import runner
from bot_moodle.routes import chat


def test_conversa_continua(monkeypatch, tmp_path):
    conn = db.conectar(str(tmp_path / "t.duckdb"))
    vistos = []
    monkeypatch.setattr(
        chat, "pedir_a_ia",
        lambda _c, p, ctx="", fix=False: vistos.append((p, ctx, fix)) or f"resp:{p}",
    )
    app = Flask(__name__)
    app.register_blueprint(chat.bp)
    chat.init_handlers(conn, None)
    cli = app.test_client()

    def enviar(i, texto):
        return cli.post("/check_and_save", json={"id": i, "texto": texto}).json

    assert enviar("1", "!chat oi")["resposta"] == "resp:oi"
    assert vistos[-1][1] == ""

    # run encerrado sozinho (sem !kill) também entra no contexto
    monkeypatch.setattr(runner, "obter_dados_run",
                        lambda: {"id": "2", "codigo": "int main(){}", "inputs": ["5"], "saida": "42"})
    enviar("3", "!fix e agora?")
    _, ctx, fix = vistos[-1]
    assert fix and "[Aluno]: !chat oi\n[IA]: resp:oi" in ctx
    assert "int main(){}" in ctx and "  5" in ctx and "42" in ctx
    assert ctx.index("resp:oi") < ctx.index("int main")

    enviar("4", "!chata parte1")
    enviar("5", "!chatsend parte2")
    assert vistos[-1][0] == "parte1\nparte2"
    assert "resp:e agora?" in vistos[-1][1]

    monkeypatch.setattr(runner, "obter_dados_run", lambda: None)  # esquecer_run zera o real
    assert "Conversa limpa" in enviar("6", "!chclear")["resposta"]
    enviar("7", "!chat de novo")
    assert vistos[-1][1] == ""
    assert enviar("7", "!chat de novo") == {"status": "duplicate"}
