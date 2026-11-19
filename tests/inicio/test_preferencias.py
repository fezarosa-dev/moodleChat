"""O menu do start: padrões, primeira vez, jeitos de conectar com reserva, chaves e o .env."""

import builtins

import pytest
from dotenv import dotenv_values

from bot_moodle.inicio import preferencias


@pytest.fixture(name="digitar")
def fixture_digitar(monkeypatch):
    """Simula o que a pessoa digita: cada input() ou getpass() pega a próxima resposta da lista."""
    respostas = []

    def proxima(*_args, **_kwargs):
        return respostas.pop(0)

    monkeypatch.setattr(builtins, "input", proxima)
    monkeypatch.setattr(preferencias.getpass, "getpass", proxima)
    return respostas


@pytest.fixture(name="terminal")
def fixture_terminal(monkeypatch, tmp_path):
    """Um terminal de verdade (isatty) e um .env vazio numa pasta temporária."""
    monkeypatch.setattr(preferencias, "ENV", tmp_path / ".env")
    monkeypatch.setattr(preferencias.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(preferencias.sys, "argv", ["preferencias"])
    return tmp_path / ".env"


# ── ler as escolhas ──────────────────────────────────────────────────────────

def test_sem_nada_no_env_usa_o_padrao():
    assert preferencias.pref("BOT_IAS") == preferencias.PADROES["BOT_IAS"]


def test_valor_do_env_vence_o_padrao(monkeypatch):
    monkeypatch.setenv("BOT_IAS", "gemini")
    assert preferencias.lista("BOT_IAS") == ["gemini"]


def test_nome_antigo_do_modo_do_moodle_ainda_vale(monkeypatch):
    monkeypatch.setenv("BOT_MOODLE_MODO", "extensao")
    assert preferencias.lista("BOT_MOODLE_MODOS") == ["extensao"]


def test_sem_bot_configurado_e_a_primeira_vez(monkeypatch):
    assert preferencias.primeira_vez()
    monkeypatch.setenv("BOT_CONFIGURADO", "1")
    assert not preferencias.primeira_vez()


def test_resumo_mostra_a_ordem_das_ias_e_das_reservas(monkeypatch):
    monkeypatch.setenv("BOT_IAS", "gemini,claude_cli")
    monkeypatch.setenv("BOT_MOODLE_MODOS", "api,extensao")
    monkeypatch.setenv("BOT_IG_LOGIN", "sessionid,senha")
    resumo = preferencias.resumo()
    assert resumo.index("Gemini") < resumo.index("Claude Code")
    assert "Moodle (API → extensão)" in resumo and "Instagram (sessionid → senha)" in resumo


# ── perguntas ────────────────────────────────────────────────────────────────

def test_configurar_pergunta_so_o_que_vale_para_as_escolhas(digitar, capsys):
    # IAs "1 3"; CLI modelo e effort; Gemini; "Só Moodle"; "Só extensão"; vigia; chave do Gemini
    digitar += ["1 3", "2", "", "", "2", "2", "", ""]
    novos = preferencias.configurar()
    assert novos["BOT_IAS"] == "claude_cli,gemini" and novos["BOT_CLI_MODELO"] == "sonnet"
    assert novos["BOT_PLATAFORMAS"] == "moodle" and novos["BOT_MOODLE_MODOS"] == "extensao"
    assert novos["BOT_CONFIGURADO"] == "1"
    assert "Como o bot entra no Instagram" not in capsys.readouterr().out
    assert not digitar  # não sobrou pergunta sem fazer


def test_reserva_do_moodle_e_do_instagram(digitar):
    # Gemini; modelo; Moodle + Instagram; "extensão, se falhar API"; "sessionid, se falhar senha";
    # vigia; chaves: API_KEY, MOODLE_URL, MOODLE_TOKEN, IG_USERNAME, IG_THREAD, IG_SESSIONID,
    # IG_PASSWORD, IG_TOTP_SEED
    digitar += ["3", "", "1", "4", "4", ""] + [""] * 8
    novos = preferencias.configurar()
    assert novos["BOT_MOODLE_MODOS"] == "extensao,api" and novos["BOT_IG_LOGIN"] == "sessionid,senha"


def test_pede_as_chaves_que_as_escolhas_precisam(digitar):
    # Gemini; modelo; Só Moodle; Só API; vigia; API_KEY; MOODLE_URL (Enter = padrão); MOODLE_TOKEN
    digitar += ["3", "", "2", "1", "", "chave-gemini", "", "moodlemobile://token=abc"]
    novos = preferencias.configurar()
    assert novos["API_KEY"] == "chave-gemini"
    assert novos["MOODLE_URL"] == "https://moodle.unifei.edu.br"
    assert novos["MOODLE_TOKEN"] == "moodlemobile://token=abc"


def test_enter_mantem_a_chave_que_ja_existe(digitar, monkeypatch):
    monkeypatch.setenv("API_KEY", "antiga")
    digitar += ["3", "", "2", "2", "", ""]  # ... só extensão; vigia; API_KEY: Enter
    assert "API_KEY" not in preferencias.configurar()


def test_chave_secreta_e_pedida_sem_aparecer_na_tela(digitar, monkeypatch):
    pedidas = []
    monkeypatch.setattr(preferencias.getpass, "getpass", lambda texto: pedidas.append(texto) or "x")
    digitar += ["3", "", "2", "2", ""]
    preferencias.configurar()
    assert any("Chave do Gemini" in texto for texto in pedidas)


@pytest.mark.parametrize("invalida", ["4", "1 1", "a", "0"])
def test_ordem_invalida_pergunta_de_novo(digitar, invalida):
    digitar += [invalida, "2 1"]
    assert preferencias._ordem_ias() == "claude_api,claude_cli"  # pylint: disable=protected-access


def test_opcao_invalida_pergunta_de_novo(digitar):
    digitar += ["9", "x", "1"]
    assert preferencias._perguntar("Teste", "b", ["a", "b"]) == "a"  # pylint: disable=protected-access


def test_enter_mantem_a_opcao_atual(digitar):
    digitar += [""]
    assert preferencias._perguntar("Teste", "b", ["a", "b"]) == "b"  # pylint: disable=protected-access


# ── salvar ───────────────────────────────────────────────────────────────────

def test_salvar_troca_as_linhas_existentes_e_acrescenta_as_novas(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# comentário\nAPI_KEY=x\nBOT_IAS=gemini\n")
    preferencias.salvar({"BOT_IAS": "claude_api,gemini", "BOT_VIGIA": "0"}, env)
    assert env.read_text() == "# comentário\nAPI_KEY=x\nBOT_IAS=claude_api,gemini\nBOT_VIGIA=0\n"


@pytest.mark.parametrize("senha", ["abc #1", "com espaço", "aspa'simples", "tudo ' e \" junto"])
def test_salvar_valor_com_caracteres_especiais_le_de_volta_igual(tmp_path, senha):
    env = tmp_path / ".env"
    preferencias.salvar({"IG_PASSWORD": senha}, env)
    assert dotenv_values(env)["IG_PASSWORD"] == senha


# ── o menu ───────────────────────────────────────────────────────────────────

def test_primeira_vez_abre_o_menu_sozinho_e_marca_configurado(terminal, digitar, capsys):
    digitar += ["3", "", "2", "2", "", ""]
    preferencias.main()
    assert "Primeira vez" in capsys.readouterr().out
    assert dotenv_values(terminal)["BOT_CONFIGURADO"] == "1"


def test_ja_configurado_enter_usa_as_escolhas_salvas(terminal, digitar, monkeypatch):
    monkeypatch.setenv("BOT_CONFIGURADO", "1")
    digitar += [""]
    preferencias.main()
    assert not terminal.exists()


def test_config_abre_o_menu_mesmo_ja_configurado(terminal, digitar, monkeypatch):
    monkeypatch.setenv("BOT_CONFIGURADO", "1")
    monkeypatch.setattr(preferencias.sys, "argv", ["preferencias", "--config"])
    digitar += ["3", "", "2", "2", "", ""]
    preferencias.main()
    assert dotenv_values(terminal)["BOT_IAS"] == "gemini"


def test_sem_terminal_nao_pergunta_nada(monkeypatch, capsys):
    monkeypatch.setattr(preferencias.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(builtins, "input", lambda *_: pytest.fail("não devia perguntar"))
    preferencias.main()
    assert "rode o start num terminal" in capsys.readouterr().out
