"""Quebra por bytes e ciclo da DM do Instagram (sem rede: cliente do IG falso)."""

from datetime import datetime, timedelta
from types import SimpleNamespace

from flask import Flask

from bot_moodle import db, instagram
from bot_moodle.routes import chat


def test_dividir_por_bytes():
    assert instagram.dividir("oi") == ["oi"]
    texto = "\n".join(f"linha {i} çãé 🙂" for i in range(200))
    partes = instagram.dividir(texto)
    assert len(partes) > 1
    assert all(len(p.encode()) <= instagram.LIMITE_BYTES for p in partes)
    assert partes[0].startswith(f"(1/{len(partes)}) ")
    # corta em quebra de linha: juntando as partes (sem prefixo) volta o texto original
    assert "\n".join(p.split(") ", 1)[1] for p in partes) == texto
    # sem espaço nem \n: corta no meio sem partir emoji (decode estrito não falha)
    for p in instagram.dividir("🙂" * 1000):
        p.encode().decode("utf-8")


def test_ciclo(monkeypatch, tmp_path):
    monkeypatch.setattr(chat, "pedir_a_ia", lambda _c, p, ctx="", fix=False: "x " * 600)
    monkeypatch.setattr(instagram, "PAUSA_PARTES", 0)
    app = Flask(__name__)
    app.register_blueprint(chat.bp)
    chat.init_handlers(db.conectar(str(tmp_path / "t.duckdb")), None)

    def msg(i, texto):
        return SimpleNamespace(id=i, text=texto, timestamp=datetime(2026, 1, 1) + timedelta(seconds=i))

    enviadas = []

    class FakeIG:  # pylint: disable=missing-class-docstring
        msgs = [msg(1, "!chat antiga"), msg(2, "conversa normal"), msg(3, "!chat oi")]

        def direct_messages(self, _tid, amount=20):  # pylint: disable=missing-function-docstring
            return self.msgs[-amount:]

        def direct_send(self, texto, **_kw):  # pylint: disable=missing-function-docstring
            enviadas.append(texto)
            m = msg(100 + len(enviadas), texto)
            self.msgs.append(m)
            return m

    ig, cliente, pular = FakeIG(), app.test_client(), {1}  # 1 = histórico da 1ª execução
    instagram._ciclo(ig, cliente, 7, pular)  # pylint: disable=protected-access
    assert len(enviadas) == 2 and enviadas[0].startswith("(1/2) ")  # só o !chat oi, quebrado
    instagram._ciclo(ig, cliente, 7, pular)  # pylint: disable=protected-access
    assert len(enviadas) == 2  # dedup no banco; respostas do bot não são reprocessadas


def test_login_sessionid_trava_conta(monkeypatch, tmp_path):
    import instagrapi  # pylint: disable=import-outside-toplevel
    import pytest  # pylint: disable=import-outside-toplevel

    class FakeClient:  # pylint: disable=missing-class-docstring,missing-function-docstring
        user_id, username = None, "outra_conta"

        def __init__(self, **_kw):
            pass

        def login_by_sessionid(self, _sid):
            self.user_id = 1

        def dump_settings(self, _p):
            pass

    monkeypatch.setattr(instagrapi, "Client", FakeClient)
    monkeypatch.setattr(instagram, "SESSAO", tmp_path / "s.json")
    monkeypatch.setenv("IG_USERNAME", "@minha_conta")
    monkeypatch.setenv("IG_SESSIONID", "x")
    monkeypatch.delenv("IG_PASSWORD", raising=False)
    with pytest.raises(RuntimeError, match="outra_conta"):
        instagram.login()
    FakeClient.username = "Minha_Conta"
    assert instagram.login().username == "Minha_Conta"

    monkeypatch.delenv("IG_THREAD", raising=False)
    assert instagram.faltando() == ["IG_THREAD"]  # sessionid substitui a senha
    monkeypatch.delenv("IG_SESSIONID")
    assert instagram.faltando() == ["IG_THREAD", "IG_PASSWORD (ou IG_SESSIONID)"]
