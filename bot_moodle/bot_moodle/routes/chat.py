"""Handlers das rotas do bot — um handler por comando."""

import re
from flask import Blueprint, request, jsonify

from bot_moodle.core import runner
from bot_moodle.core.ai import pedir_a_ia
from bot_moodle import db as _db_module

bp = Blueprint("chat", __name__)

# Quantos itens (pergunta+resposta ou run) da conversa vão como contexto para a IA
LIMITE_CONTEXTO = 20

# Injetados em bot_moodle/app.py após criar o app
_db_conn   = None
_ai_client = None


def init_handlers(db_conn, ai_client) -> None:
    """Injeta dependências (DB e cliente IA) nos handlers."""
    global _db_conn, _ai_client  # pylint: disable=global-statement
    _db_conn   = db_conn
    _ai_client = ai_client


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────

def _pendente() -> "str | None":
    """Retorna resultado pendente do runner ou None."""
    return runner.verificar_resultado_pendente()


def _juntar(pendente: "str | None", msg: str) -> str:
    """Une resultado pendente e mensagem com separador quando ambos existem."""
    if pendente:
        return f"{pendente}\n{'─' * 40}\n{msg}"
    return msg


def _ia(pergunta: str, contexto: str = "", fix: bool = False) -> str:
    return pedir_a_ia(_ai_client, pergunta, contexto, fix)


def _salvar_run_atual(cursor) -> None:
    """Persiste o run em memória no banco, se houver."""
    dados = runner.obter_dados_run()
    if dados and dados["id"]:
        _db_module.salvar_run(
            cursor,
            dados["id"],
            dados["codigo"] or "",
            dados["inputs"],
            dados["saida"] or "",
        )


def _contexto_conversa(cursor) -> str:
    """Monta a conversa desde o último !chclear (perguntas, respostas e runs)."""
    blocos = []
    for tipo, a, b, c in _db_module.buscar_conversa(cursor, LIMITE_CONTEXTO):
        if tipo == "chat":
            blocos.append(f"[Aluno]: {a}\n[IA]: {b}")
        else:
            entradas = "\n".join(f"  {v}" for v in b) or "  (nenhuma)"
            blocos.append(
                f"[Aluno executou !run]\nCódigo:\n{a}\n\n"
                f"Entradas:\n{entradas}\n\nSaída:\n{c or '(sem saída registrada)'}"
            )
    return "\n\n".join(blocos)


def _responder(cursor, msg_id, pergunta, pendente, fix=False):
    """Chama a IA com a conversa como contexto e grava a resposta no histórico."""
    if not pergunta:
        return jsonify({
            "status": "new", "is_command": True,
            "resposta": _juntar(pendente, "Digite sua dúvida ou código após o comando."),
        }), 200
    _salvar_run_atual(cursor)  # run encerrado sozinho ainda não foi persistido
    resposta = _ia(pergunta, contexto=_contexto_conversa(cursor), fix=fix)
    _db_module.salvar_resposta_ia(cursor, f"r_{msg_id}", msg_id, resposta)
    return jsonify({
        "status": "new", "is_command": True,
        "resposta": _juntar(pendente, resposta),
    }), 200


# ─────────────────────────────────────────────
#  TEXTO DE AJUDA
# ─────────────────────────────────────────────

def _ajuda() -> str:
    return (
        "📋 GUIA DE COMANDOS DO BOT ACADÊMICO\n\n"
        "1. IA (conversa contínua, como um chat normal):\n"
        "   !chat <pergunta>   -> Pergunta para a IA.\n"
        "   !fix <código>      -> Pede a correção de um bug.\n"
        f"   A IA lembra das últimas {LIMITE_CONTEXTO} interações (perguntas e !run)\n"
        "   até você usar !chclear. Código C da resposta é testado antes de chegar.\n\n"
        "2. MENSAGEM GRANDE (maior que o limite do chat):\n"
        "   !chata <parte>     -> Guarda uma parte sem chamar a IA.\n"
        "   !chatsend [texto]  -> Junta as partes e envia como uma pergunta só.\n\n"
        "3. EXECUÇÃO DE CÓDIGO C:\n"
        "   !run <código C>    -> Compila e executa.\n"
        "   !r <valor>         -> Envia uma entrada para o programa.\n"
        "   !kill              -> Encerra e entrega toda a saída acumulada.\n"
        f"   A saída chega após {runner.SILENCE_TIMEOUT:g}s sem novo output ou com !kill.\n\n"
        "4. OUTROS:\n"
        "   !chclear           -> Limpa a conversa (perguntas, respostas e runs).\n"
        "   !help              -> Mostra este menu."
    )


# ─────────────────────────────────────────────
#  HANDLERS
# ─────────────────────────────────────────────

def _handle_help(pendente):
    return jsonify({
        "status": "new", "is_command": True,
        "resposta": _juntar(pendente, _ajuda()),
    }), 200


def _handle_run(cursor, msg_id, texto, pendente):
    codigo = texto[4:].strip()
    if not codigo:
        return jsonify({
            "status": "new", "is_command": True,
            "resposta": "❌ Envie o código após !run. Exemplo: !run int main(){...}",
        }), 200
    _pendente()  # descarta pendente anterior
    resultado = runner.compilar_e_executar(codigo, run_id=msg_id)
    return jsonify({"status": "new", "is_command": True, "resposta": resultado}), 200


def _handle_r(pendente, texto):
    valor = texto[2:].strip()
    if not valor:
        return jsonify({
            "status": "new", "is_command": True,
            "resposta": _juntar(pendente, "❌ Envie o valor após !r. Exemplo: !r 42"),
        }), 200
    resultado = runner.enviar_input(valor)
    if pendente and ("encerrou" in resultado or "Nenhum programa" in resultado):
        return jsonify({"status": "new", "is_command": True, "resposta": pendente}), 200
    return jsonify({
        "status": "new", "is_command": True,
        "resposta": _juntar(pendente, resultado),
    }), 200


def _handle_kill(cursor):
    _salvar_run_atual(cursor)
    resultado = runner.matar_processo()
    return jsonify({"status": "new", "is_command": True, "resposta": resultado}), 200


def _handle_chclear(cursor, pendente):
    qtd = _db_module.limpar_historico_chat(cursor)
    runner.esquecer_run()
    msg = f"🧹 Conversa limpa. {qtd} mensagem(ns) removida(s) do banco."
    return jsonify({
        "status": "new", "is_command": True,
        "resposta": _juntar(pendente, msg),
    }), 200


def _handle_chata(cursor, msg_id, texto, pendente):
    parte = texto[len("!chata"):].strip()
    if not parte:
        msg = "❌ Envie o texto após !chata. Exemplo: !chata primeira parte..."
    else:
        qtd = _db_module.adicionar_buffer(cursor, msg_id, parte)
        msg = f"📥 Parte {qtd} guardada. Envie mais com !chata ou finalize com !chatsend."
    return jsonify({
        "status": "new", "is_command": True,
        "resposta": _juntar(pendente, msg),
    }), 200


def _handle_chatsend(cursor, msg_id, texto, pendente):
    final = texto[len("!chatsend"):].strip()
    partes = _db_module.consumir_buffer(cursor) + ([final] if final else [])
    if not partes:
        return jsonify({
            "status": "new", "is_command": True,
            "resposta": _juntar(pendente, "📭 Buffer vazio. Use !chata <texto> antes."),
        }), 200
    pergunta = "\n".join(partes)
    # Grava o texto completo no histórico para a conversa enxergar a pergunta inteira
    cursor.execute(
        "UPDATE mensagens_usuario SET texto = ? WHERE id = ?",
        (f"!chat {pergunta}", msg_id),
    )
    return _responder(cursor, msg_id, pergunta, pendente)


def _handle_ia(cursor, msg_id, texto, pendente):
    """Processa !chat / !fix; None se não for comando de IA."""
    m = re.match(r"^!(chat|fix)", texto)
    if not m:
        return None
    pergunta = texto[m.end():].strip()
    return _responder(cursor, msg_id, pergunta, pendente, fix=m.group(1) == "fix")


# ─────────────────────────────────────────────
#  ROTA PRINCIPAL
# ─────────────────────────────────────────────

@bp.route("/check_and_save", methods=["POST"])
def check_and_save():
    """Recebe mensagem do Moodle, processa e retorna resposta."""
    data   = request.json
    msg_id = data.get("id")
    texto  = data.get("texto", "").strip()

    cursor = _db_conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO mensagens_usuario (id, texto) VALUES (?, ?)"
            " ON CONFLICT (id) DO NOTHING",
            (msg_id, texto),
        )
        # DuckDB não preenche rowcount (-1); a contagem de linhas inseridas vem no resultado
        if cursor.fetchone()[0] == 0:
            return jsonify({"status": "duplicate"}), 200

        pendente = _pendente()

        if texto.startswith("!help"):
            return _handle_help(pendente)
        if texto.startswith("!run"):
            _salvar_run_atual(cursor)
            return _handle_run(cursor, msg_id, texto, pendente)
        if texto.startswith("!r ") or texto == "!r":
            return _handle_r(pendente, texto)
        if texto == "!kill":
            return _handle_kill(cursor)
        if texto == "!chclear":
            return _handle_chclear(cursor, pendente)
        if re.match(r"^!chata(\s|$)", texto):
            return _handle_chata(cursor, msg_id, texto, pendente)
        if re.match(r"^!chatsend(\s|$)", texto):
            return _handle_chatsend(cursor, msg_id, texto, pendente)

        resp = _handle_ia(cursor, msg_id, texto, pendente)
        if resp is not None:
            return resp

        if pendente:
            return jsonify({"status": "new", "is_command": True, "resposta": pendente}), 200
        return jsonify({"status": "new", "is_command": False}), 200

    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"[Erro no Servidor]: {exc}")
        # 200 com resposta para o erro aparecer no chat (a extensão ignora não-"new")
        return jsonify({
            "status": "new", "is_command": True,
            "resposta": f"❌ Erro no servidor: {exc}",
        }), 200
    finally:
        cursor.close()
