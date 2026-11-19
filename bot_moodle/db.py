"""O banco local (DuckDB): mensagens, respostas da IA, runs e o buffer do !chata.

Fica em dados/moodle_history.duckdb (DB_FILE no .env) e é compartilhado entre Moodle e
Instagram. Os ids das mensagens servem para não responder a mesma mensagem duas vezes.
"""

import json
from pathlib import Path

import duckdb

from bot_moodle import caminhos

# Schema das tabelas — adicione novas tabelas aqui
_SCHEMA = """
CREATE TABLE IF NOT EXISTS mensagens_usuario (
    id          VARCHAR PRIMARY KEY,
    texto       TEXT,
    data_envio  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS respostas_ia (
    id              VARCHAR PRIMARY KEY,
    msg_usuario_id  VARCHAR,
    texto_resposta  TEXT,
    status          VARCHAR DEFAULT 'sucesso',
    data_resposta   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (msg_usuario_id) REFERENCES mensagens_usuario(id)
);

CREATE TABLE IF NOT EXISTS runs (
    id        VARCHAR PRIMARY KEY,
    codigo    TEXT,
    inputs    TEXT,
    saida     TEXT,
    data_run  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS buffer_chat (
    msg_id      VARCHAR PRIMARY KEY,
    texto       TEXT,
    data_envio  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""
# as mensagens que fazem parte da conversa com a IA
_E_CONVERSA = "texto LIKE '!chat%' OR texto LIKE '!fix%'"


def conectar(db_file: str = str(caminhos.BANCO)) -> duckdb.DuckDBPyConnection:
    """Abre (ou cria) o banco DuckDB e garante que o schema existe."""
    Path(db_file).parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(db_file, read_only=False)
    conn.execute(_SCHEMA)
    return conn


# ── runs ─────────────────────────────────────────────────────────────────────

def salvar_run(
    cursor: duckdb.DuckDBPyConnection,
    run_id: str,
    codigo: str,
    inputs: list,
    saida: str,
) -> None:
    """Persiste (ou atualiza) um run no banco."""
    cursor.execute(
        """
        INSERT INTO runs (id, codigo, inputs, saida)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (id) DO UPDATE
        SET codigo=excluded.codigo,
            inputs=excluded.inputs,
            saida=excluded.saida
        """,
        (run_id, codigo, json.dumps(inputs), saida or ""),
    )


# ── histórico da conversa ────────────────────────────────────────────────────

def _lista_de_entradas(texto_json: "str | None") -> list:
    try:
        return json.loads(texto_json) if texto_json else []
    except ValueError:
        return []


def buscar_conversa(
    cursor: duckdb.DuckDBPyConnection, limite: int
) -> list[tuple]:
    """
    Últimos `limite` itens da conversa (desde o último !chclear), do mais antigo
    ao mais novo. Cada item: ("chat", pergunta, resposta, None)
    ou ("run", codigo, inputs_list, saida).
    """
    rows = cursor.execute(
        """
        SELECT * FROM (
            SELECT u.data_envio AS t, 'chat' AS tipo,
                   u.texto AS a, r.texto_resposta AS b, NULL AS c
            FROM mensagens_usuario u
            JOIN respostas_ia r ON u.id = r.msg_usuario_id
            WHERE (u.texto LIKE '!chat%' OR u.texto LIKE '!fix%')
              AND r.status = 'sucesso'
            UNION ALL
            SELECT data_run, 'run', codigo, inputs, saida FROM runs
        )
        ORDER BY t DESC
        LIMIT ?
        """,
        (limite,),
    ).fetchall()
    return [(tipo, a, _lista_de_entradas(b) if tipo == "run" else b, c)
            for _, tipo, a, b, c in reversed(rows)]


def salvar_resposta_ia(
    cursor: duckdb.DuckDBPyConnection,
    resp_id: str,
    msg_id: str,
    texto: str,
) -> None:
    """Insere uma resposta da IA no banco."""
    cursor.execute(
        "INSERT INTO respostas_ia (id, msg_usuario_id, texto_resposta, status)"
        " VALUES (?, ?, ?, 'sucesso')",
        (resp_id, msg_id, texto),
    )


def limpar_historico_chat(cursor: duckdb.DuckDBPyConnection) -> int:
    """
    Zera a conversa: histórico de !chat/!fix (respostas + texto das mensagens;
    os ids ficam para o dedup), runs salvos e o buffer de !chata.
    Retorna a quantidade de mensagens removidas.
    """
    qtd = cursor.execute(f"SELECT COUNT(*) FROM mensagens_usuario WHERE {_E_CONVERSA}").fetchone()[0]
    cursor.execute("DELETE FROM respostas_ia WHERE msg_usuario_id IN"
                   f" (SELECT id FROM mensagens_usuario WHERE {_E_CONVERSA})")
    # mantém a linha (o id é o registro de dedup) e só apaga o texto: apagar a linha faria as
    # mensagens antigas ainda visíveis no Moodle serem respondidas de novo
    cursor.execute(f"UPDATE mensagens_usuario SET texto = NULL WHERE {_E_CONVERSA}")
    cursor.execute("DELETE FROM runs")
    cursor.execute("DELETE FROM buffer_chat")

    return qtd


# ── buffer de mensagem grande (!chata / !chatsend) ───────────────────────────

def adicionar_buffer(
    cursor: duckdb.DuckDBPyConnection, msg_id: str, texto: str
) -> int:
    """Guarda uma parte no buffer; retorna o total de partes guardadas."""
    cursor.execute(
        "INSERT INTO buffer_chat (msg_id, texto) VALUES (?, ?)", (msg_id, texto)
    )
    return cursor.execute("SELECT COUNT(*) FROM buffer_chat").fetchone()[0]


def consumir_buffer(cursor: duckdb.DuckDBPyConnection) -> list[str]:
    """Retorna as partes em ordem de envio e esvazia o buffer."""
    partes = [
        r[0]
        for r in cursor.execute(
            "SELECT texto FROM buffer_chat ORDER BY data_envio, msg_id"
        ).fetchall()
    ]
    cursor.execute("DELETE FROM buffer_chat")
    return partes
