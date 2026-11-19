"""A linha de reserva: ordem das IAs, reserva quando uma falha, prompt e avisos dos testes."""

import pytest

from bot_moodle.ia import linha

CODIGO = "#include <stdio.h>\nint main(void){}"


@pytest.fixture(name="chamadas")
def fixture_chamadas(monkeypatch):
    """IAs falsas: claude_cli falha, claude_api responde, gemini falha. Guarda a ordem das chamadas."""
    chamadas = []

    def falha(nome):
        def provedor(_cliente, _prompt):
            chamadas.append(nome)
            raise RuntimeError("cota estourada")
        return provedor

    def responde(_cliente, _prompt):
        chamadas.append("claude_api")
        return CODIGO, {"testou": True, "passou": True}

    monkeypatch.setitem(linha.PROVEDORES, "claude_cli", falha("claude_cli"))
    monkeypatch.setitem(linha.PROVEDORES, "claude_api", responde)
    monkeypatch.setitem(linha.PROVEDORES, "gemini", falha("gemini"))
    monkeypatch.setenv("BOT_IAS", "claude_cli,claude_api,gemini")
    return chamadas


def test_se_a_primeira_falha_a_proxima_responde(chamadas):
    assert linha.pedir_a_ia(None, "oi") == CODIGO
    assert chamadas == ["claude_cli", "claude_api"]  # o gemini nem é chamado


def test_a_que_falhou_e_tentada_de_novo_na_mensagem_seguinte(chamadas):
    linha.pedir_a_ia(None, "oi")
    linha.pedir_a_ia(None, "oi")
    assert chamadas == ["claude_cli", "claude_api"] * 2


def test_segue_a_ordem_do_menu(chamadas, monkeypatch):
    monkeypatch.setenv("BOT_IAS", "gemini,claude_api")
    linha.pedir_a_ia(None, "oi")
    assert chamadas == ["gemini", "claude_api"]


def test_ia_fora_da_linha_nao_e_chamada(chamadas, monkeypatch):
    monkeypatch.setenv("BOT_IAS", "gemini")
    assert linha.pedir_a_ia(None, "oi") == linha.TODAS_FALHARAM
    assert chamadas == ["gemini"]


def test_nome_desconhecido_na_linha_e_ignorado(chamadas, monkeypatch):
    monkeypatch.setenv("BOT_IAS", "ia_que_nao_existe,claude_api")
    assert linha.pedir_a_ia(None, "oi") == CODIGO
    assert chamadas == ["claude_api"]


def test_resposta_vazia_conta_como_falha(chamadas, monkeypatch):
    monkeypatch.setitem(linha.PROVEDORES, "claude_cli", lambda _c, _p: ("", None))
    assert linha.pedir_a_ia(None, "oi") == CODIGO
    assert chamadas == ["claude_api"]


def test_avisa_quando_o_codigo_nao_passou(monkeypatch):
    monkeypatch.setitem(linha.PROVEDORES, "gemini",
                        lambda _c, _p: (CODIGO, {"testou": True, "passou": False}))
    monkeypatch.setenv("BOT_IAS", "gemini")
    assert linha.pedir_a_ia(None, "oi").endswith("⚠️ O código não passou em todos os testes.")


@pytest.mark.parametrize("texto, estado, esperado", [
    ("int main(void){}", {"testou": False, "passou": False}, "NÃO foi testado"),
    ("#include <stdio.h>", {"testou": False, "passou": False}, "NÃO foi testado"),
    ("só uma explicação", {"testou": False, "passou": False}, ""),
    ("int main(void){}", {"testou": True, "passou": False}, "não passou"),
    ("int main(void){}", {"testou": True, "passou": True}, ""),
    ("int main(void){}", None, ""),  # o Claude Code testa sozinho
])
def test_aviso_dos_testes(texto, estado, esperado):
    aviso = linha.aviso(texto, estado)
    assert (esperado in aviso) if esperado else aviso == ""


def test_prompt_tem_regras_conversa_e_pergunta():
    prompt = linha.montar_prompt("o que é ponteiro?", contexto="[Aluno]: oi\n[IA]: olá")
    assert "tutor acadêmico" in prompt and "texto puro" in prompt
    assert "CONVERSA ATÉ AQUI" in prompt and "[Aluno]: oi" in prompt
    assert prompt.endswith("SOLICITAÇÃO ATUAL: o que é ponteiro?")
    assert prompt.index("[Aluno]: oi") < prompt.index("SOLICITAÇÃO ATUAL")


def test_prompt_sem_conversa_nao_tem_bloco_de_contexto():
    assert "CONVERSA ATÉ AQUI" not in linha.montar_prompt("oi")


def test_prompt_do_fix_pede_correcao():
    assert "debugging" in linha.montar_prompt("int main(", modo_fix=True)
    assert "debugging" not in linha.montar_prompt("int main(")
