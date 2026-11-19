"""Quebra por bytes e ciclo da DM do Instagram (sem rede: cliente do IG falso)."""

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from flask import Flask

from bot_moodle import db
from bot_moodle.plataformas import instagram
from bot_moodle import comandos as chat


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


@pytest.fixture(name="cliente_falso")
def fixture_cliente_falso(monkeypatch):
    """Troca o Client do instagrapi: `falsos.falham` diz quais jeitos de login dão erro e
    `falsos.conta` é a conta em que ele entra. `falsos.tentados` guarda a ordem das tentativas."""
    import instagrapi  # pylint: disable=import-outside-toplevel

    falsos = SimpleNamespace(falham=set(), conta="minha_conta", tentados=[])

    class ClienteFalso:  # pylint: disable=missing-function-docstring
        username = None

        def __init__(self, **_kwargs):
            pass

        def _entrar(self, jeito):
            falsos.tentados.append(jeito)
            if jeito in falsos.falham:
                raise RuntimeError(f"{jeito} recusado")
            self.username = falsos.conta

        def login(self, _usuario, _senha, verification_code=""):
            falsos.codigo = verification_code
            self._entrar("senha")

        def login_by_sessionid(self, _sid):
            self._entrar("sessionid")

        def totp_generate_code(self, semente):
            return f"codigo-de-{semente}"

        def dump_settings(self, _caminho):
            pass

    monkeypatch.setattr(instagrapi, "Client", ClienteFalso)
    monkeypatch.setenv("IG_USERNAME", "@minha_conta")
    monkeypatch.setenv("IG_PASSWORD", "senha")
    monkeypatch.setenv("IG_SESSIONID", "cookie")
    return falsos


def test_login_usa_o_primeiro_jeito_da_ordem(cliente_falso, monkeypatch):
    monkeypatch.setenv("BOT_IG_LOGIN", "sessionid,senha")
    entrada = instagram.entrar()
    assert entrada.jeito == "sessionid" and cliente_falso.tentados == ["sessionid"]


def test_se_o_primeiro_jeito_falha_usa_a_reserva(cliente_falso, monkeypatch):
    monkeypatch.setenv("BOT_IG_LOGIN", "senha,sessionid")
    cliente_falso.falham = {"senha"}
    entrada = instagram.entrar()
    assert entrada.jeito == "sessionid" and "senha recusado" in entrada.falhas[0]


def test_sem_reserva_o_erro_aparece(cliente_falso, monkeypatch):
    monkeypatch.setenv("BOT_IG_LOGIN", "senha")
    cliente_falso.falham = {"senha"}
    with pytest.raises(RuntimeError, match="nenhum jeito de login funcionou: senha"):
        instagram.entrar()
    assert cliente_falso.tentados == ["senha"]


def test_jeito_sem_dado_no_env_e_pulado(cliente_falso, monkeypatch):  # pylint: disable=unused-argument
    monkeypatch.setenv("BOT_IG_LOGIN", "sessionid,senha")
    monkeypatch.delenv("IG_SESSIONID")
    assert instagram.entrar().jeito == "senha"


def test_senha_usa_o_codigo_do_2fa(cliente_falso, monkeypatch):
    monkeypatch.setenv("BOT_IG_LOGIN", "senha")
    monkeypatch.setenv("IG_TOTP_SEED", "abcd efgh")
    instagram.entrar()
    assert cliente_falso.codigo == "codigo-de-ABCDEFGH"  # sem espaços e em maiúsculas


def test_trava_nunca_usa_outra_conta(cliente_falso, monkeypatch):
    monkeypatch.setenv("BOT_IG_LOGIN", "sessionid")
    cliente_falso.conta = "outra_conta"
    with pytest.raises(RuntimeError, match="outra_conta"):
        instagram.entrar()


def test_conta_com_maiusculas_diferentes_e_a_mesma(cliente_falso, monkeypatch):
    monkeypatch.setenv("BOT_IG_LOGIN", "sessionid")
    cliente_falso.conta = "Minha_Conta"
    assert instagram.login().username == "Minha_Conta"


def test_faltando_lista_o_que_precisa_no_env(monkeypatch):
    monkeypatch.setenv("BOT_IG_LOGIN", "senha,sessionid")
    monkeypatch.setenv("IG_USERNAME", "conta")
    assert instagram.faltando() == ["IG_THREAD", "IG_PASSWORD ou IG_SESSIONID"]
    monkeypatch.setenv("IG_THREAD", "dm")
    monkeypatch.setenv("IG_SESSIONID", "cookie")
    assert instagram.faltando() == []  # o sessionid basta (é reserva da senha)


def test_causa_mostra_o_motivo_sem_o_payload():
    erro = RuntimeError("needs_upgrade")
    erro.caa_initial_outcome = {"reason": "senha errada", "x": [{"y": "CAA_ETAPA:2"}, "outro"]}
    causa = instagram.causa(erro)
    assert "'senha errada'" in causa and "CAA_ETAPA:2" in causa and "outro" not in causa
