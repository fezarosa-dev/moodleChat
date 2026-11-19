"""As checagens do start: cada linha começa com OK, AVISO, PULA, ERRO ou DICA (o script desenha)."""

import socket

import pytest

from bot_moodle import ia
from bot_moodle.inicio import checagens
from bot_moodle.plataformas import moodle


def linhas(capsys) -> list[str]:
    return capsys.readouterr().out.splitlines()


# ── IAs ──────────────────────────────────────────────────────────────────────

@pytest.fixture(name="ias")
def fixture_ias(monkeypatch):
    """IAs falsas: o dicionário diz o que cada uma responde (texto) ou a exceção que levanta."""
    respostas = {}

    def chamar(nome, _cliente, _prompt):
        resposta = respostas[nome]
        if isinstance(resposta, Exception):
            raise resposta
        return resposta, {"modelo": "gemini-2.5-flash"} if nome == "gemini" else None

    monkeypatch.setattr(ia, "chamar", chamar)
    return respostas


def test_ia_que_responde_e_ok(ias, monkeypatch, capsys):
    monkeypatch.setenv("BOT_IAS", "claude_cli")
    ias["claude_cli"] = "ok"
    checagens.ias()
    assert linhas(capsys) == ["OK Claude Code (CLI) responde (opus, medium)"]


def test_ia_que_falha_vira_aviso_e_continua_na_linha(ias, monkeypatch, capsys):
    monkeypatch.setenv("BOT_IAS", "claude_api,claude_cli")
    ias["claude_api"] = RuntimeError("sem chave\ndetalhes")
    ias["claude_cli"] = "ok"
    checagens.ias()
    saida = linhas(capsys)
    assert saida[0].startswith("AVISO Claude API") and "sem chave" in saida[0]
    assert "continua na linha" in saida[0] and "detalhes" not in saida[0]
    assert saida[1].startswith("OK Claude Code")


def test_gemini_mostra_o_modelo_que_respondeu(ias, monkeypatch, capsys):
    monkeypatch.setenv("BOT_IAS", "gemini")
    monkeypatch.setenv("BOT_GEMINI_MODELO", "gemini-3.5-flash")
    ias["gemini"] = "ok"
    checagens.ias()
    assert "respondeu com gemini-2.5-flash" in linhas(capsys)[0]


def test_nenhuma_ia_respondendo_e_erro(ias, monkeypatch, capsys):
    monkeypatch.setenv("BOT_IAS", "gemini")
    ias["gemini"] = RuntimeError("fora do ar")
    checagens.ias()
    saida = linhas(capsys)
    assert saida[1].startswith("ERRO Nenhuma IA") and saida[2].startswith("DICA")


def test_linha_vazia_e_erro(monkeypatch, capsys):
    monkeypatch.setenv("BOT_IAS", "nenhuma_conhecida")
    checagens.ias()
    assert linhas(capsys)[0] == "ERRO Nenhuma IA escolhida"


# ── Moodle pela API ──────────────────────────────────────────────────────────

@pytest.fixture(name="ws")
def fixture_ws(monkeypatch):
    """O ws do Moodle falso: devolve `ws.resposta` ou levanta as exceções de `ws.erros`, em ordem."""
    class WsFalso:  # pylint: disable=too-few-public-methods
        erros: list = []
        resposta = {"fullname": "FULANO", "functions": [{"name": f} for f in moodle.FUNCOES]}

        def __call__(self, _funcao, **_args):
            if self.erros:
                raise self.erros.pop(0)
            return self.resposta

    falso = WsFalso()
    monkeypatch.setattr(moodle, "ws", falso)
    monkeypatch.setenv("MOODLE_URL", "https://moodle.exemplo.br")
    monkeypatch.setenv("MOODLE_TOKEN", "abc")
    return falso


def test_moodle_com_chave_valida_e_ok(ws, capsys):  # pylint: disable=unused-argument
    checagens.moodle_api()
    assert linhas(capsys) == ["OK Moodle pela API como FULANO (sem extensão)"]


def test_moodle_sem_chave_avisa_e_ensina_a_pegar(monkeypatch, capsys):
    monkeypatch.delenv("MOODLE_TOKEN", raising=False)
    monkeypatch.setenv("MOODLE_URL", "https://moodle.exemplo.br")
    checagens.moodle_api()
    saida = linhas(capsys)
    assert saida[0].startswith("AVISO") and "MOODLE_TOKEN" in saida[0]
    assert saida[1].startswith("DICA") and "launch.php" in saida[1]


def test_moodle_com_chave_vencida_avisa(ws, capsys):
    ws.erros = [moodle.ChaveInvalida("Token inválido")]
    checagens.moodle_api()
    saida = linhas(capsys)
    assert "não vale mais" in saida[0] and saida[1].startswith("DICA")


def test_moodle_tenta_de_novo_se_a_rede_cai_uma_vez(ws, monkeypatch, capsys):
    monkeypatch.setattr(checagens.time, "sleep", lambda _s: None)
    ws.erros = [ConnectionResetError("reset")]
    checagens.moodle_api()
    assert linhas(capsys)[0].startswith("OK")


def test_moodle_fora_do_ar_avisa(ws, monkeypatch, capsys):
    monkeypatch.setattr(checagens.time, "sleep", lambda _s: None)
    ws.erros = [OSError("fora"), OSError("fora")]
    checagens.moodle_api()
    assert "tenta de novo a cada 30 s" in linhas(capsys)[0]


def test_moodle_sem_as_funcoes_de_mensagem_avisa(ws, capsys):
    ws.resposta = {"fullname": "FULANO", "functions": []}
    checagens.moodle_api()
    assert "não libera" in linhas(capsys)[0]


# ── porta e plano ────────────────────────────────────────────────────────────

def test_porta_livre_e_ok(monkeypatch, capsys):
    with socket.socket() as livre:
        livre.bind(("127.0.0.1", 0))
        numero = livre.getsockname()[1]
    monkeypatch.setenv("PORT", str(numero))
    checagens.porta()
    assert linhas(capsys)[0] == f"OK Porta {numero} livre para a extensão"


def test_porta_ocupada_e_erro(monkeypatch, capsys):
    with socket.create_server(("127.0.0.1", 0)) as ocupada:
        monkeypatch.setenv("PORT", str(ocupada.getsockname()[1]))
        checagens.porta()
    assert linhas(capsys)[0].startswith("ERRO Porta")


def test_porta_ocupada_na_reserva_e_so_aviso(monkeypatch, capsys):
    with socket.create_server(("127.0.0.1", 0)) as ocupada:
        monkeypatch.setenv("PORT", str(ocupada.getsockname()[1]))
        assert not checagens.porta("Reserva: ", obrigatoria=False)
    assert linhas(capsys)[0].startswith("AVISO Reserva: Porta")


def test_moodle_testa_cada_jeito_da_sequencia(monkeypatch, capsys):
    monkeypatch.setattr(checagens, "moodle_api", lambda prefixo="": print(f"api[{prefixo}]") or False)
    monkeypatch.setattr(checagens, "porta", lambda prefixo="", obrigatoria=True: print(f"porta[{prefixo}]") or False)
    checagens.moodle_em_ordem(("api", "extensao"))
    assert linhas(capsys) == ["api[]", "porta[Reserva: ]",
                              "AVISO Moodle: nenhum jeito de conectar funcionou (sobe sem ele)"]


@pytest.mark.parametrize("plataformas, modos, esperado", [
    ("moodle,instagram", "api", ["ias", "instagram", "moodle_api"]),
    ("moodle", "extensao", ["ias", "PULA", "porta"]),
    ("instagram", "api", ["ias", "instagram", "PULA"]),
    ("moodle", "api,extensao", ["ias", "PULA", "moodle_api", "porta"]),
])
def test_so_checa_o_que_foi_escolhido(monkeypatch, capsys, plataformas, modos, esperado):
    monkeypatch.setenv("BOT_PLATAFORMAS", plataformas)
    monkeypatch.setenv("BOT_MOODLE_MODOS", modos)
    for nome in ("ias", "instagram", "moodle_api", "porta"):
        monkeypatch.setattr(checagens, nome, lambda *_a, n=nome, **_k: print(n) or True)
    checagens.main()
    assert [linha.split()[0] for linha in linhas(capsys)] == esperado
