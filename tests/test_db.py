"""O banco (DuckDB): histórico da conversa, runs, buffer do !chata e o !chclear."""

import pytest

from bot_moodle import db


@pytest.fixture(name="cursor")
def fixture_cursor(tmp_path):
    return db.conectar(str(tmp_path / "teste.duckdb")).cursor()


def mensagem(cursor, msg_id, texto, resposta=None):
    """Grava uma mensagem do aluno (e a resposta da IA, se houver)."""
    cursor.execute("INSERT INTO mensagens_usuario (id, texto) VALUES (?, ?)", (msg_id, texto))
    if resposta is not None:
        db.salvar_resposta_ia(cursor, f"r_{msg_id}", msg_id, resposta)


def test_conectar_de_novo_no_mesmo_arquivo_mantem_os_dados(tmp_path):
    arquivo = str(tmp_path / "teste.duckdb")
    conexao = db.conectar(arquivo)
    mensagem(conexao.cursor(), "1", "!chat oi", "olá")
    conexao.close()
    assert db.buscar_conversa(db.conectar(arquivo).cursor(), 10) == [("chat", "!chat oi", "olá", None)]


def test_conversa_tem_so_chat_e_fix_respondidos(cursor):
    mensagem(cursor, "1", "!chat oi", "olá")
    mensagem(cursor, "2", "conversa normal")
    mensagem(cursor, "3", "!help", "guia")
    mensagem(cursor, "4", "!fix int main(", "corrigido")
    assert [item[1] for item in db.buscar_conversa(cursor, 10)] == ["!chat oi", "!fix int main("]


def test_conversa_traz_os_mais_recentes_do_mais_antigo_ao_mais_novo(cursor):
    for i in range(5):
        mensagem(cursor, str(i), f"!chat {i}", f"r{i}")
    assert [item[2] for item in db.buscar_conversa(cursor, 3)] == ["r2", "r3", "r4"]


def test_run_entra_na_conversa_com_as_entradas_em_lista(cursor):
    db.salvar_run(cursor, "9", "int main(){}", ["5", "7"], "12")
    assert db.buscar_conversa(cursor, 10) == [("run", "int main(){}", ["5", "7"], "12")]


def test_salvar_o_mesmo_run_de_novo_atualiza(cursor):
    db.salvar_run(cursor, "9", "v1", [], "")
    db.salvar_run(cursor, "9", "v2", ["1"], "saída")
    assert db.buscar_conversa(cursor, 10) == [("run", "v2", ["1"], "saída")]


def test_entradas_corrompidas_viram_lista_vazia(cursor):
    cursor.execute("INSERT INTO runs (id, codigo, inputs, saida) VALUES ('1', 'c', 'não é json', '')")
    assert db.buscar_conversa(cursor, 10)[0][2] == []


def test_chclear_apaga_a_conversa_mas_guarda_os_ids(cursor):
    mensagem(cursor, "1", "!chat oi", "olá")
    mensagem(cursor, "2", "!fix x", "y")
    db.salvar_run(cursor, "9", "c", [], "")
    db.adicionar_buffer(cursor, "3", "parte")
    assert db.limpar_historico_chat(cursor) == 2
    assert db.buscar_conversa(cursor, 10) == [] and db.consumir_buffer(cursor) == []
    # o id continua lá: a mesma mensagem, vista de novo no Moodle, não é respondida duas vezes
    assert cursor.execute("SELECT COUNT(*) FROM mensagens_usuario").fetchone()[0] == 2


def test_buffer_guarda_conta_e_devolve_na_ordem(cursor):
    assert db.adicionar_buffer(cursor, "1", "primeira") == 1
    assert db.adicionar_buffer(cursor, "2", "segunda") == 2
    assert db.consumir_buffer(cursor) == ["primeira", "segunda"]
    assert db.consumir_buffer(cursor) == []  # consumir esvazia
