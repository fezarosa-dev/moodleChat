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

CREATE TABLE IF NOT EXISTS estado_pendente (
    id_sessao           INTEGER PRIMARY KEY DEFAULT 1,
    msg_id              VARCHAR,
    texto_original      TEXT,
    contexto_acumulado  TEXT
);

CREATE TABLE IF NOT EXISTS runs (
    id        VARCHAR PRIMARY KEY,
    codigo    TEXT,
    inputs    TEXT,
    saida     TEXT,
    data_run  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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


def buscar_run(cursor: duckdb.DuckDBPyConnection, run_id: str) -> "dict | None":
    """Busca um run pelo ID; retorna dict ou None."""
    row = cursor.execute(
        "SELECT codigo, inputs, saida FROM runs WHERE id = ?", (run_id,)
    ).fetchone()
    if not row:
        return None
    codigo, inputs_json, saida = row
    try:
        inputs = json.loads(inputs_json) if inputs_json else []
    except ValueError:
        inputs = []
    return {"codigo": codigo, "inputs": inputs, "saida": saida}


# ─────────────────────────────────────────────────────────────────────────────
#  HISTÓRICO DE CHAT
# ─────────────────────────────────────────────────────────────────────────────

def buscar_historico(
    cursor: duckdb.DuckDBPyConnection, limite: int
) -> list[tuple]:
    """Retorna as últimas `limite` interações com resposta bem-sucedida."""
    return cursor.execute(
        """
        SELECT u.id, u.texto, r.texto_resposta
        FROM mensagens_usuario u
        JOIN respostas_ia r ON u.id = r.msg_usuario_id
        WHERE (u.texto LIKE '!chat%' OR u.texto LIKE '!fix%')
          AND r.status = 'sucesso'
        ORDER BY u.data_envio DESC
        LIMIT ?
        """,
        (limite,),
    ).fetchall()


def buscar_mensagem(
    cursor: duckdb.DuckDBPyConnection, msg_id: str
) -> "tuple | None":
    """Retorna (texto_usuario, texto_ia, status_ia) ou None."""
    return cursor.execute(
        """
        SELECT u.texto, r.texto_resposta, r.status
        FROM mensagens_usuario u
        LEFT JOIN respostas_ia r ON u.id = r.msg_usuario_id
        WHERE u.id = ?
        """,
        (msg_id,),
    ).fetchone()


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


def buscar_estado_pendente(
    cursor: duckdb.DuckDBPyConnection,
) -> "tuple | None":
    """Retorna (msg_id, texto_original, contexto_acumulado) ou None."""
    return cursor.execute(
        "SELECT msg_id, texto_original, contexto_acumulado"
        " FROM estado_pendente WHERE id_sessao = 1"
    ).fetchone()


def salvar_estado_pendente(
    cursor: duckdb.DuckDBPyConnection,
    msg_id: str,
    texto_original: str,
    contexto: str,
) -> None:
    """Upsert do estado pendente (só há 1 por sessão)."""
    cursor.execute(
        """
        INSERT INTO estado_pendente
            (id_sessao, msg_id, texto_original, contexto_acumulado)
        VALUES (1, ?, ?, ?)
        ON CONFLICT (id_sessao) DO UPDATE
        SET msg_id=excluded.msg_id,
            texto_original=excluded.texto_original,
            contexto_acumulado=excluded.contexto_acumulado
        """,
        (msg_id, texto_original, contexto),
    )


def deletar_estado_pendente(cursor: duckdb.DuckDBPyConnection) -> None:
    """Remove o estado pendente da sessão."""
    cursor.execute("DELETE FROM estado_pendente WHERE id_sessao = 1")
