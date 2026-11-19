"""Comandos do chat (!chat, !fix, !chata, !chatsend, !chclear, !help, !run…).

Cada teste descreve um comportamento do bot visto de fora: manda mensagens como o Moodle ou o
Instagram mandariam e confere a resposta. A IA é falsa (veja conftest.py).
"""

from bot_moodle import comandos
from bot_moodle.execucao import runner


# ── mensagens que não são comandos ───────────────────────────────────────────

def test_mensagem_sem_exclamacao_so_e_registrada(enviar, ia):
    assert enviar("oi, tudo bem?") == {"status": "new", "is_command": False}
    assert not ia.chamadas


def test_comando_desconhecido_nao_responde(enviar):
    assert enviar("!naoexiste")["is_command"] is False


def test_mesma_mensagem_duas_vezes_e_respondida_uma_vez_so(enviar, ia):
    enviar("!chat oi", msg_id="42")
    assert enviar("!chat oi", msg_id="42") == {"status": "duplicate"}
    assert len(ia.chamadas) == 1


# ── IA: !chat e !fix ─────────────────────────────────────────────────────────

def test_chat_manda_a_pergunta_para_a_ia(enviar, ia):
    resposta = enviar("!chat o que é ponteiro?")
    assert resposta == {"status": "new", "is_command": True, "resposta": "resp:o que é ponteiro?"}
    assert ia.ultima == ("o que é ponteiro?", "", False)


def test_fix_pede_correcao(enviar, ia):
    enviar("!fix int main(){")
    assert ia.ultima[2] is True


def test_pergunta_pode_comecar_na_linha_de_baixo(enviar, ia):
    enviar("!fix\nint main(void) {\n    return 0;\n}")
    assert ia.ultima[0] == "int main(void) {\n    return 0;\n}"


def test_chat_sem_pergunta_pede_o_texto(enviar, ia):
    assert "Digite sua dúvida" in enviar("!chat")["resposta"]
    assert not ia.chamadas


def test_conversa_continua_leva_o_historico_para_a_ia(enviar, ia):
    enviar("!chat oi")
    enviar("!fix e agora?")
    _, contexto, _ = ia.ultima
    assert "[Aluno]: !chat oi\n[IA]: resp:oi" in contexto


def test_run_encerrado_entra_no_contexto(enviar, ia, monkeypatch):
    monkeypatch.setattr(runner, "obter_dados_run",
                        lambda: {"id": "9", "codigo": "int main(){}", "inputs": ["5"], "saida": "42"})
    enviar("!chat oi")
    enviar("!chat e o run?")
    _, contexto, _ = ia.ultima
    assert "int main(){}" in contexto and "  5" in contexto and "42" in contexto


# ── mensagem grande: !chata e !chatsend ──────────────────────────────────────

def test_chata_guarda_as_partes_sem_chamar_a_ia(enviar, ia):
    assert "Parte 1 guardada" in enviar("!chata primeira")["resposta"]
    assert "Parte 2 guardada" in enviar("!chata segunda")["resposta"]
    assert not ia.chamadas


def test_chata_sem_texto_explica_o_uso(enviar):
    assert "Envie o texto após !chata" in enviar("!chata")["resposta"]


def test_chatsend_junta_as_partes_e_o_texto_final(enviar, ia):
    enviar("!chata parte1")
    enviar("!chata parte2")
    assert enviar("!chatsend o que faz?")["resposta"] == "resp:parte1\nparte2\no que faz?"
    assert ia.ultima[0] == "parte1\nparte2\no que faz?"


def test_chatsend_esvazia_as_partes(enviar):
    enviar("!chata parte1")
    enviar("!chatsend")
    assert "Buffer vazio" in enviar("!chatsend")["resposta"]


def test_chatsend_grava_a_pergunta_inteira_no_historico(enviar, ia):
    enviar("!chata parte1")
    enviar("!chatsend parte2")
    enviar("!chat e então?")
    assert "[Aluno]: !chat parte1\nparte2" in ia.ultima[1]


# ── !chclear e !help ─────────────────────────────────────────────────────────

def test_chclear_apaga_a_conversa(enviar, ia, monkeypatch):
    monkeypatch.setattr(runner, "obter_dados_run", lambda: None)
    enviar("!chat oi")
    assert "Conversa limpa. 1 mensagem(ns)" in enviar("!chclear")["resposta"]
    enviar("!chat de novo")
    assert ia.ultima[1] == ""


def test_help_lista_os_comandos(enviar):
    ajuda = enviar("!help")["resposta"]
    for comando in ("!chat", "!fix", "!chata", "!chatsend", "!chclear", "!help"):
        assert comando in ajuda
    assert "!run" not in ajuda  # desativado


def test_help_mostra_o_run_quando_ativo(enviar, monkeypatch):
    monkeypatch.setattr(comandos, "RUN_ATIVO", True)
    assert "!run <código C>" in enviar("!help")["resposta"]


# ── execução direta (desativada) e saída pendente ────────────────────────────

def test_run_r_e_kill_desativados_avisam(enviar):
    for texto in ("!run int main(){}", "!r 5", "!kill"):
        assert "desativados" in enviar(texto)["resposta"]


def test_saida_pendente_vem_antes_da_resposta(enviar, monkeypatch):
    monkeypatch.setattr(runner, "verificar_resultado_pendente", lambda: "saída do programa")
    resposta = enviar("!chat oi")["resposta"]
    assert resposta.startswith("saída do programa\n") and resposta.endswith("resp:oi")


def test_saida_pendente_chega_mesmo_sem_comando(enviar, monkeypatch):
    monkeypatch.setattr(runner, "verificar_resultado_pendente", lambda: "saída do programa")
    assert enviar("conversa normal") == {
        "status": "new", "is_command": True, "resposta": "saída do programa"}


# ── erros ────────────────────────────────────────────────────────────────────

def test_erro_inesperado_vira_resposta_no_chat(enviar, monkeypatch):
    def quebrar(*_args, **_kwargs):
        raise RuntimeError("banco caiu")

    monkeypatch.setattr(comandos, "pedir_a_ia", quebrar)
    assert enviar("!chat oi")["resposta"] == "❌ Erro no servidor: banco caiu"
