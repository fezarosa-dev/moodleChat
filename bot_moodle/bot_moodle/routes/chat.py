"""Handlers das rotas do bot — um handler por comando."""

import re
from flask import Blueprint, request, jsonify

from bot_moodle.core import runner
from bot_moodle.core.ai import pedir_ao_gemini
from bot_moodle import db as _db_module

bp = Blueprint("chat", __name__)

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


def _gemini(pergunta: str, contexto: str = "", fix: bool = False) -> str:
    return pedir_ao_gemini(_ai_client, pergunta, contexto, fix)


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


def _contexto_run(cursor, run_id: str) -> "str | None":
    """Busca run e monta bloco de contexto para a IA. None se não encontrado."""
    row = _db_module.buscar_run(cursor, run_id)
    if not row:
        return None
    inputs_fmt = (
        "\n".join(f"  {v}" for v in row["inputs"])
        if row["inputs"]
        else "  (nenhum)"
    )
    return (
        f"[Run ID {run_id}]\n"
        f"Código:\n{row['codigo']}\n\n"
        f"Entradas fornecidas:\n{inputs_fmt}\n\n"
        f"Saída do programa:\n{row['saida'] or '(sem saída registrada)'}\n"
    )


def _resolver_run_id(cursor, texto: str) -> "tuple[str, str | None]":
    """
    Detecta +<id> no texto.
    Retorna (texto_sem_plus_id, contexto_ou_aviso_de_erro).
    """
    m = re.search(r"\+(\S+)", texto)
    if not m:
        return texto, None
    run_id    = m.group(1)
    texto_sem = (texto[: m.start()] + texto[m.end():]).strip()
    ctx = _contexto_run(cursor, run_id)
    if ctx is None:
        return texto_sem, f"⚠️ Run ID '{run_id}' não encontrado no banco."
    return texto_sem, ctx


# ─────────────────────────────────────────────
#  TEXTO DE AJUDA
# ─────────────────────────────────────────────

def _ajuda() -> str:
    return (
        "📋 GUIA DE COMANDOS DO BOT ACADÊMICO:\n\n"
        "1. COMANDOS DE IA:\n"
        "   !chat <pergunta>        -> Pergunta normal para a IA.\n"
        "   !fix <código>           -> Correção direta de bugs.\n"
        "   !chat+<id> <pergunta>   -> Inclui o run de <id> como contexto.\n"
        "   !fix+<id> <código>      -> Fix com contexto do run de <id>.\n"
        "   !help                   -> Exibe este menu.\n\n"
        "2. CONTEXTO POR QUANTIDADE:\n"
        "   !chatN <pergunta>       -> Puxa as últimas N interações.\n"
        "   Exemplo: !chat3 por que o ponteiro falhou?\n\n"
        "3. CONTEXTO CIRÚRGICO POR ID:\n"
        "   !chatid<regras> <pergunta>\n"
        "   IDt -> pergunta E resposta  |  IDm -> só pergunta  |  IDr -> só resposta\n"
        "   Exemplo: !chatid8t,9m,10r qual a relação entre eles?\n\n"
        "4. EXECUÇÃO DE CÓDIGO C:\n"
        "   !run <código C>  -> Compila e executa.\n"
        "   !r <valor>       -> Envia input para o programa.\n"
        "   !kill            -> Encerra e entrega toda a saída acumulada.\n"
        "   (Saída entregue após 5s de silêncio ou com !kill)"
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


def _handle_confirmacao(cursor, msg_id, texto, pendente):
    estado = _db_module.buscar_estado_pendente(cursor)
    if not estado:
        return jsonify({
            "status": "new", "is_command": True,
            "resposta": _juntar(
                pendente, "Não há nenhuma ação aguardando confirmação no momento."
            ),
        }), 200

    orig_msg_id, texto_original, contexto_acumulado = estado
    _db_module.deletar_estado_pendente(cursor)

    if texto == "!n":
        return jsonify({
            "status": "new", "is_command": True,
            "resposta": _juntar(pendente, "Operação cancelada."),
        }), 200

    modo_fix = texto_original.startswith("!fix")
    pergunta = re.sub(r"^!(chat\d*|chatid[^\s]*|fix)", "", texto_original).strip()
    resposta = _gemini(pergunta, contexto=contexto_acumulado, fix=modo_fix)
    _db_module.salvar_resposta_ia(cursor, f"r_{orig_msg_id}", orig_msg_id, resposta)
    return jsonify({
        "status": "new", "is_command": True,
        "resposta": _juntar(pendente, f"{resposta}\n\nID: {orig_msg_id}"),
    }), 200


def _handle_ia(cursor, msg_id, texto, pendente):  # noqa: C901
    """Processa !chat / !chatN / !chatid / !fix com suporte a +id."""
    is_chat_num    = re.match(r"^!chat(\d+)", texto)
    is_chat_id     = texto.startswith("!chatid")
    is_fix         = texto.startswith("!fix")
    is_chat_normal = (
        texto.startswith("!chat") and not is_chat_num and not is_chat_id
    )

    if not (is_chat_normal or is_fix or is_chat_num or is_chat_id):
        return None

    contexto = ""
    pergunta = ""

    # ── !chatN ───────────────────────────────────────────────────────────────
    if is_chat_num:
        limite = int(is_chat_num.group(1))
        resto  = texto.replace(is_chat_num.group(0), "").strip()
        resto, ctx_run = _resolver_run_id(cursor, resto)
        pergunta = resto

        historico = _db_module.buscar_historico(cursor, limite)
        qtd = len(historico)
        for h_id, h_user, h_ia in reversed(historico):
            contexto += f"[Usuário ID {h_id}]: {h_user}\n[IA]: {h_ia}\n\n"
        if ctx_run:
            contexto += ctx_run + "\n"

        if qtd < limite:
            _db_module.salvar_estado_pendente(cursor, msg_id, texto, contexto)
            aviso = (
                f"⚠️ Só foi possível localizar {qtd} interação(ões) com resposta "
                f"válida (você pediu {limite}). Deseja prosseguir mesmo assim?\n"
                "Responda !s para SIM ou !n para NÃO."
            )
            return jsonify({
                "status": "new", "is_command": True,
                "resposta": _juntar(pendente, aviso),
            }), 200

    # ── !chatid ───────────────────────────────────────────────────────────────
    elif is_chat_id:
        match_regra = re.match(r"^!chatid([^\s]+)", texto)
        regras_str  = match_regra.group(1)
        resto       = texto.replace(match_regra.group(0), "").strip()
        resto, ctx_run = _resolver_run_id(cursor, resto)
        pergunta = resto

        falhas: list[str] = []
        ctx_temp = ""

        for regra in regras_str.split(","):
            regra = regra.strip()
            if not regra:
                continue
            m = re.match(r"^(.+?)([tmr])$", regra)
            if not m:
                falhas.append(f"'{regra}' (formato inválido, use IDt / IDm / IDr)")
                continue
            target_id, tipo = m.group(1), m.group(2)
            dados = _db_module.buscar_mensagem(cursor, target_id)
            if not dados:
                falhas.append(f"ID {target_id} (não encontrado no banco)")
                continue
            u_txt, r_txt, r_status = dados
            if tipo in ("t", "r"):
                if not r_txt or not r_txt.strip():
                    falhas.append(f"ID {target_id} (resposta da IA está vazia)")
                    continue
                if r_status and r_status != "sucesso":
                    falhas.append(
                        f"ID {target_id} (resposta marcada como '{r_status}')"
                    )
                    continue
            if tipo == "t":
                ctx_temp += (
                    f"[Histórico ID {target_id} - Msg]: {u_txt}\n"
                    f"[Histórico ID {target_id} - Resp]: {r_txt}\n\n"
                )
            elif tipo == "m":
                ctx_temp += f"[Histórico ID {target_id} - Msg]: {u_txt}\n\n"
            elif tipo == "r":
                ctx_temp += f"[Histórico ID {target_id} - Resp]: {r_txt}\n\n"

        if falhas:
            msg_err = (
                "⚠️ Erro de Integridade — os seguintes IDs não puderam ser incluídos:\n"
                + "\n".join(f"  • {f}" for f in falhas)
                + "\n\nA operação foi abortada. Corrija as regras e tente novamente."
            )
            return jsonify({
                "status": "new", "is_command": True,
                "resposta": _juntar(pendente, msg_err),
            }), 200

        contexto = ctx_temp + (ctx_run + "\n" if ctx_run else "")

    # ── !chat simples ou !fix ─────────────────────────────────────────────────
    else:
        cmd  = "!fix" if is_fix else "!chat"
        resto = texto.replace(cmd, "", 1).strip()
        resto, ctx_run = _resolver_run_id(cursor, resto)
        pergunta = resto
        if ctx_run:
            contexto = ctx_run + "\n"

    if not pergunta:
        return jsonify({
            "status": "new", "is_command": True,
            "resposta": _juntar(
                pendente, "Digite sua dúvida ou código após o comando."
            ),
        }), 200

    resposta = _gemini(pergunta, contexto=contexto, fix=bool(is_fix))
    _db_module.salvar_resposta_ia(cursor, f"r_{msg_id}", msg_id, resposta)
    return jsonify({
        "status": "new", "is_command": True,
        "resposta": _juntar(pendente, f"{resposta}\n\nID: {msg_id}"),
    }), 200


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
        if cursor.rowcount == 0:
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
        if texto in ("!s", "!n"):
            return _handle_confirmacao(cursor, msg_id, texto, pendente)

        resp = _handle_ia(cursor, msg_id, texto, pendente)
        if resp is not None:
            return resp

        if pendente:
            return jsonify({"status": "new", "is_command": True, "resposta": pendente}), 200
        return jsonify({"status": "new", "is_command": False}), 200

    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"[Erro no Servidor]: {exc}")
        return jsonify({"error": str(exc)}), 500
    finally:
        cursor.close()
