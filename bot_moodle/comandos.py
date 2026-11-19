"""Os comandos do chat (!chat, !fix, !chata, !chatsend, !chclear, !help e o !run desativado).

Moodle (API ou extensão) e Instagram mandam cada mensagem para a rota /check_and_save. Ela
registra a mensagem (uma vez só por id), escolhe o comando numa tabela e devolve a resposta.
"""

import re
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from flask import Blueprint, jsonify, request

from bot_moodle import db
from bot_moodle.execucao import runner
from bot_moodle.ia import pedir_a_ia

bp = Blueprint("chat", __name__)

# Quantos itens (pergunta+resposta ou run) da conversa vão como contexto para a IA
LIMITE_CONTEXTO = 20

# !run / !r / !kill desativados por enquanto (a IA já compila e testa o código).
# O código continua aqui: troque para True para reativar.
RUN_ATIVO = False

SEPARADOR = "─" * 40
RUN_DESATIVADO = ("⏸️ !run/!r/!kill estão desativados no momento. "
                  "Para testar código, peça à IA: !chat roda esse código com a entrada ...")

# Fila: Moodle e Instagram chegam em threads diferentes; processa uma mensagem por vez
# para o histórico compartilhado não intercalar. ponytail: Lock não garante ordem FIFO
# estrita, mas com poucas mensagens a ordem de chegada se mantém na prática.
_fila = threading.Lock()

@dataclass
class _Dependencias:
    """O banco e o cliente do Gemini, injetados por app.create_app (e pelos testes)."""

    banco: Any = None        # a conexão do DuckDB
    cliente_ia: Any = None   # o cliente do Gemini (None sem API_KEY)


_dependencias = _Dependencias()


def init_handlers(db_conn, ai_client) -> None:
    """Injeta o banco e o cliente da IA usados pelos comandos."""
    _dependencias.banco, _dependencias.cliente_ia = db_conn, ai_client


@dataclass
class Mensagem:
    """Uma mensagem recebida, já separada em comando e argumento."""

    cursor: object
    id: str
    texto: str
    comando: str = ""
    argumento: str = ""

    @classmethod
    def ler(cls, cursor, msg_id: str, texto: str) -> "Mensagem":
        """"!chat oi" -> comando "chat", argumento "oi". Sem "!" no início, não há comando."""
        partes = re.match(r"!(\w+)\s*(.*)", texto, re.DOTALL)
        if not partes:
            return cls(cursor, msg_id, texto)
        return cls(cursor, msg_id, texto, partes.group(1), partes.group(2).strip())


# ── conversa com a IA ────────────────────────────────────────────────────────

def _juntar(pendente: "str | None", texto: str) -> str:
    """Põe a saída pendente de um !run antes da resposta."""
    return f"{pendente}\n{SEPARADOR}\n{texto}" if pendente else texto


def _salvar_run_atual(cursor) -> None:
    """Grava no banco o !run que está em memória, se houver."""
    dados = runner.obter_dados_run()
    if not (dados and dados["id"]):
        return
    db.salvar_run(cursor, dados["id"], dados["codigo"] or "", dados["inputs"], dados["saida"] or "")


def _bloco_de_contexto(tipo: str, a, b, c) -> str:
    if tipo == "chat":
        return f"[Aluno]: {a}\n[IA]: {b}"
    entradas = "\n".join(f"  {v}" for v in b) or "  (nenhuma)"
    return (f"[Aluno executou !run]\nCódigo:\n{a}\n\n"
            f"Entradas:\n{entradas}\n\nSaída:\n{c or '(sem saída registrada)'}")


def _contexto_conversa(cursor) -> str:
    """A conversa desde o último !chclear (perguntas, respostas e runs), da mais antiga à mais nova."""
    return "\n\n".join(_bloco_de_contexto(*item)
                       for item in db.buscar_conversa(cursor, LIMITE_CONTEXTO))


def _perguntar(msg: Mensagem, pergunta: str, modo_fix: bool = False) -> str:
    """Chama a IA com a conversa como contexto e grava a resposta no histórico."""
    if not pergunta:
        return "Digite sua dúvida ou código após o comando."
    _salvar_run_atual(msg.cursor)  # um run que terminou sozinho ainda não foi gravado
    resposta = pedir_a_ia(_dependencias.cliente_ia, pergunta, _contexto_conversa(msg.cursor), modo_fix)
    db.salvar_resposta_ia(msg.cursor, f"r_{msg.id}", msg.id, resposta)
    return resposta


# ── comandos (cada um devolve o texto da resposta) ───────────────────────────

def _chat(msg: Mensagem) -> str:
    return _perguntar(msg, msg.argumento)


def _fix(msg: Mensagem) -> str:
    return _perguntar(msg, msg.argumento, modo_fix=True)


def _chata(msg: Mensagem) -> str:
    if not msg.argumento:
        return "❌ Envie o texto após !chata. Exemplo: !chata primeira parte..."
    quantidade = db.adicionar_buffer(msg.cursor, msg.id, msg.argumento)
    return f"📥 Parte {quantidade} guardada. Envie mais com !chata ou finalize com !chatsend."


def _chatsend(msg: Mensagem) -> str:
    partes = db.consumir_buffer(msg.cursor) + ([msg.argumento] if msg.argumento else [])
    if not partes:
        return "📭 Buffer vazio. Use !chata <texto> antes."
    pergunta = "\n".join(partes)
    # o histórico guarda a pergunta inteira, para a conversa seguinte enxergá-la
    msg.cursor.execute("UPDATE mensagens_usuario SET texto = ? WHERE id = ?",
                       (f"!chat {pergunta}", msg.id))
    return _perguntar(msg, pergunta)


def _chclear(msg: Mensagem) -> str:
    quantidade = db.limpar_historico_chat(msg.cursor)
    runner.esquecer_run()
    return f"🧹 Conversa limpa. {quantidade} mensagem(ns) removida(s) do banco."


def _help(_msg: Mensagem) -> str:
    return ajuda()


def ajuda() -> str:
    """O guia de comandos que o !help mostra."""
    execucao = (
        "EXECUÇÃO DE CÓDIGO C:\n"
        "   !run <código C>    -> Compila e executa.\n"
        "   !r <valor>         -> Envia uma entrada para o programa.\n"
        "   !kill              -> Encerra e entrega toda a saída acumulada.\n"
        f"   A saída chega após {runner.SILENCE_TIMEOUT:g}s sem novo output ou com !kill.\n\n"
    ) if RUN_ATIVO else ""
    return (
        "📋 GUIA DE COMANDOS DO BOT ACADÊMICO\n\n"
        "IA (conversa contínua, como um chat normal):\n"
        "   !chat <pergunta>   -> Pergunta para a IA.\n"
        "   !fix <código>      -> Pede a correção de um bug.\n"
        f"   A IA lembra das últimas {LIMITE_CONTEXTO} interações até você usar !chclear.\n"
        "   Código C da resposta é compilado e testado antes de chegar;\n"
        "   para rodar o seu código, peça: !chat roda esse código com a entrada 5 ...\n\n"
        "MENSAGEM GRANDE (maior que o limite do chat):\n"
        "   !chata <parte>     -> Guarda uma parte sem chamar a IA.\n"
        "   !chatsend [texto]  -> Junta as partes e envia como uma pergunta só.\n\n"
        + execucao +
        "OUTROS:\n"
        "   !chclear           -> Limpa a conversa.\n"
        "   !help              -> Mostra este menu."
    )


# ── execução direta (!run, !r, !kill): cuidam da saída pendente sozinhos ─────

def _run(msg: Mensagem) -> str:
    if not msg.argumento:
        return "❌ Envie o código após !run. Exemplo: !run int main(){...}"
    _salvar_run_atual(msg.cursor)
    runner.verificar_resultado_pendente()  # descarta a saída do run anterior
    return runner.compilar_e_executar(msg.argumento, run_id=msg.id)


def _r(msg: Mensagem) -> str:
    pendente = runner.verificar_resultado_pendente()
    if not msg.argumento:
        return _juntar(pendente, "❌ Envie o valor após !r. Exemplo: !r 42")
    resultado = runner.enviar_input(msg.argumento)
    programa_acabou = "encerrou" in resultado or "Nenhum programa" in resultado
    if pendente and programa_acabou:
        return pendente
    return _juntar(pendente, resultado)


def _kill(msg: Mensagem) -> str:
    # não lê a saída pendente antes: matar_processo a entrega junto (senão ela se perderia)
    _salvar_run_atual(msg.cursor)
    return runner.matar_processo()


COMANDOS: dict[str, Callable[[Mensagem], str]] = {
    "chat": _chat, "fix": _fix, "chata": _chata, "chatsend": _chatsend,
    "chclear": _chclear, "help": _help,
}
COMANDOS_RUN: dict[str, Callable[[Mensagem], str]] = {"run": _run, "r": _r, "kill": _kill}


# ── a rota ───────────────────────────────────────────────────────────────────

def _resposta(texto: str):
    return jsonify({"status": "new", "is_command": True, "resposta": texto}), 200


def _registrar(cursor, msg_id: str, texto: str) -> bool:
    """Grava a mensagem; False se o id já existia (mensagem repetida)."""
    cursor.execute("INSERT INTO mensagens_usuario (id, texto) VALUES (?, ?)"
                   " ON CONFLICT (id) DO NOTHING", (msg_id, texto))
    # o DuckDB não preenche rowcount: a quantidade de linhas inseridas vem no resultado
    return cursor.fetchone()[0] > 0


def _executar(msg: Mensagem):
    if msg.comando in COMANDOS_RUN:
        return _resposta(COMANDOS_RUN[msg.comando](msg) if RUN_ATIVO else RUN_DESATIVADO)
    pendente = runner.verificar_resultado_pendente()
    comando = COMANDOS.get(msg.comando)
    if comando:
        return _resposta(_juntar(pendente, comando(msg)))
    if pendente:
        return _resposta(pendente)
    return jsonify({"status": "new", "is_command": False}), 200


@bp.route("/check_and_save", methods=["POST"])
def check_and_save():
    """Recebe uma mensagem (Moodle ou Instagram), processa na fila e devolve a resposta."""
    dados = request.json
    texto = dados.get("texto", "").strip()
    with _fila:
        cursor = _dependencias.banco.cursor()
        try:
            if not _registrar(cursor, dados.get("id"), texto):
                return jsonify({"status": "duplicate"}), 200
            return _executar(Mensagem.ler(cursor, dados.get("id"), texto))
        except Exception as exc:  # pylint: disable=broad-exception-caught
            print(f"[Erro no Servidor]: {exc}")
            # 200 com resposta: o erro aparece no chat (a extensão ignora o que não é "new")
            return _resposta(f"❌ Erro no servidor: {exc}")
        finally:
            cursor.close()
