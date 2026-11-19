"""Peças comuns dos testes: o bot com banco temporário e uma IA falsa (sem rede, sem cota)."""

import os
from dataclasses import dataclass, field

import pytest
from flask import Flask

from bot_moodle import comandos, db
from bot_moodle.execucao import runner


# variáveis do .env que mudam o comportamento do bot: cada teste começa sem nenhuma
PREFIXOS_DO_ENV = ("BOT_", "IG_", "MOODLE_")
CHAVES_DO_ENV = {"API_KEY", "ANTHROPIC_API_KEY", "PORT", "DB_FILE"}


@pytest.fixture(name="pasta_isolada", autouse=True)
def fixture_pasta_isolada(monkeypatch, tmp_path):
    """Cada teste roda numa pasta temporária: nenhum teste lê ou escreve o .env, o banco ou as
    sessões de verdade do projeto (os caminhos do bot são relativos à pasta atual)."""
    monkeypatch.chdir(tmp_path)


@pytest.fixture(name="ambiente_limpo", autouse=True)
def fixture_ambiente_limpo(monkeypatch):
    """Os testes não dependem do .env de quem roda (no GitHub nem existe .env)."""
    for nome in list(os.environ):
        if nome.startswith(PREFIXOS_DO_ENV) or nome in CHAVES_DO_ENV:
            monkeypatch.delenv(nome)


@pytest.fixture(autouse=True)
def runner_limpo():
    """O runner guarda o !run atual em memória (estado global): cada teste começa sem nenhum."""
    yield
    runner.matar_processo()
    runner.verificar_resultado_pendente()
    runner.esquecer_run()


@dataclass
class IAFalsa:
    """Responde "resp:<pergunta>" e guarda cada chamada (pergunta, contexto, fix)."""

    chamadas: list = field(default_factory=list)

    def __call__(self, _cliente, pergunta, contexto="", modo_fix=False):
        self.chamadas.append((pergunta, contexto, modo_fix))
        return f"resp:{pergunta}"

    @property
    def ultima(self):
        """A última chamada: (pergunta, contexto, fix)."""
        return self.chamadas[-1]


@pytest.fixture(name="ia")
def fixture_ia(monkeypatch):
    """Troca a IA de verdade pela falsa em todos os comandos."""
    falsa = IAFalsa()
    monkeypatch.setattr(comandos, "pedir_a_ia", falsa)
    return falsa


@pytest.fixture(name="app")
def fixture_app(tmp_path, ia, pasta_isolada, ambiente_limpo):  # pylint: disable=unused-argument
    """O app Flask com a rota dos comandos e um banco novo em pasta temporária."""
    app = Flask(__name__)
    app.register_blueprint(comandos.bp)
    comandos.init_handlers(db.conectar(str(tmp_path / "teste.duckdb")), None)
    return app


@pytest.fixture(name="enviar")
def fixture_enviar(app):
    """Manda uma mensagem para o bot como o Moodle/Instagram faria e devolve o JSON."""
    cliente = app.test_client()
    contador = iter(range(1, 10_000))

    def enviar(texto, msg_id=None):
        msg_id = msg_id or str(next(contador))
        return cliente.post("/check_and_save", json={"id": msg_id, "texto": texto}).json

    return enviar
