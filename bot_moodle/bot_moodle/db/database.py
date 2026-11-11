"""Conexão com DuckDB e helpers de persistência."""

import json
import duckdb

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


def conectar(db_file: str = "moodle_history.duckdb") -> duckdb.DuckDBPyConnection:
    """Abre (ou cria) o banco DuckDB e garante que o schema existe."""
    conn = duckdb.connect(db_file, read_only=False)
    conn.execute(_SCHEMA)
    return conn


# ─────────────────────────────────────────────────────────────────────────────
#  RUNS
# ─────────────────────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────────────────────
#  HISTÓRICO DE CHAT
# ─────────────────────────────────────────────────────────────────────────────

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
    itens = []
    for _, tipo, a, b, c in reversed(rows):
        if tipo == "run":
            try:
                b = json.loads(b) if b else []
            except ValueError:
                b = []
        itens.append((tipo, a, b, c))
    return itens


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
    qtd = cursor.execute(
        "SELECT COUNT(*) FROM mensagens_usuario"
        " WHERE texto LIKE '!chat%' OR texto LIKE '!fix%'"
    ).fetchone()[0]

    cursor.execute(
        """
        DELETE FROM respostas_ia
        WHERE msg_usuario_id IN (
            SELECT id FROM mensagens_usuario
            WHERE texto LIKE '!chat%' OR texto LIKE '!fix%'
        )
        """
    )
    # Mantém a linha (o id é o registro de dedup); só apaga o conteúdo.
    # Deletar faria as mensagens antigas ainda visíveis no Moodle serem reprocessadas no reload.
    cursor.execute(
        "UPDATE mensagens_usuario SET texto = NULL"
        " WHERE texto LIKE '!chat%' OR texto LIKE '!fix%'"
    )
    cursor.execute("DELETE FROM runs")
    cursor.execute("DELETE FROM buffer_chat")

    return qtd


# ─────────────────────────────────────────────────────────────────────────────
#  BUFFER DE MENSAGENS QUEBRADAS (!chata / !chatsend)
# ─────────────────────────────────────────────────────────────────────────────

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
