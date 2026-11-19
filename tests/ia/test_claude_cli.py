"""Claude Code (CLI): a linha de comando e o tratamento das falhas (subprocess falso)."""

from types import SimpleNamespace as NS

import pytest

from bot_moodle.ia import claude_cli


@pytest.fixture(name="rodar")
def fixture_rodar(monkeypatch):
    """Troca o subprocess.run: devolve `rodar.resultado` e guarda os argumentos da chamada."""
    rodar = NS(resultado=NS(returncode=0, stdout="resposta\n", stderr=""), chamada=None)

    def run(comando, **kwargs):
        rodar.chamada = (comando, kwargs)
        if isinstance(rodar.resultado, Exception):
            raise rodar.resultado
        return rodar.resultado

    monkeypatch.setattr(claude_cli.subprocess, "run", run)
    return rodar


def test_manda_o_prompt_pelo_stdin_e_devolve_a_saida(rodar):
    assert claude_cli.responder(None, "oi") == ("resposta", None)
    comando, kwargs = rodar.chamada
    assert comando[1] == "-p" and kwargs["input"] == "oi" and kwargs["encoding"] == "utf-8"


def test_usa_modelo_e_effort_do_menu(monkeypatch):
    monkeypatch.setenv("BOT_CLI_MODELO", "sonnet")
    monkeypatch.setenv("BOT_CLI_EFFORT", "low")
    comando = claude_cli.comando()
    assert comando[comando.index("--model") + 1] == "sonnet"
    assert comando[comando.index("--effort") + 1] == "low"


def test_ignora_as_configuracoes_pessoais_do_claude():
    comando = claude_cli.comando()
    assert "--strict-mcp-config" in comando and "--no-session-persistence" in comando
    assert comando[comando.index("--setting-sources") + 1] == ""


def test_erro_do_claude_vira_runtime_error(rodar):
    rodar.resultado = NS(returncode=1, stdout="", stderr="Credit balance is too low\nmais")
    with pytest.raises(RuntimeError, match="código 1: Credit balance is too low"):
        claude_cli.responder(None, "oi")


def test_saida_vazia_e_falha(rodar):
    rodar.resultado = NS(returncode=0, stdout="  ", stderr="")
    with pytest.raises(RuntimeError, match="sem saída"):
        claude_cli.responder(None, "oi")


def test_sem_claude_instalado_explica_como_instalar(rodar):
    rodar.resultado = FileNotFoundError("claude")
    with pytest.raises(RuntimeError, match="instale o Claude Code"):
        claude_cli.responder(None, "oi")
