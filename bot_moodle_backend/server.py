import os
import re
from flask import Flask, request, jsonify
from flask_cors import CORS
import duckdb
from google import genai
from dotenv import load_dotenv
import run  # Módulo de compilação e execução de C

load_dotenv()

app = Flask(__name__)
CORS(app)

DB_FILE = "moodle_history.duckdb"
db_conn = duckdb.connect(DB_FILE, read_only=False)

db_conn.execute("""
CREATE TABLE IF NOT EXISTS mensagens_usuario (
    id VARCHAR PRIMARY KEY,
    texto TEXT,
    data_envio TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS respostas_ia (
    id VARCHAR PRIMARY KEY,
    msg_usuario_id VARCHAR,
    texto_resposta TEXT,
    status VARCHAR DEFAULT 'sucesso',
    data_resposta TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (msg_usuario_id) REFERENCES mensagens_usuario(id)
);

CREATE TABLE IF NOT EXISTS estado_pendente (
    id_sessao INTEGER PRIMARY KEY DEFAULT 1,
    msg_id VARCHAR,
    texto_original TEXT,
    contexto_acumulado TEXT
);
""")

API_KEY = os.getenv("API_KEY")
if not API_KEY:
    print("\n❌ [ERRO CRÍTICO]: Chave 'API_KEY' não encontrada no .env!\n")

client = genai.Client(api_key=API_KEY)


# ─────────────────────────────────────────────
#  GEMINI
# ─────────────────────────────────────────────

def pedir_ao_gemini(pergunta: str, contexto_historico: str = "", modo_fix: bool = False) -> str:
    modelos_fallback = [
        'gemini-3.5-flash', 'gemini-3-flash', 'gemini-2.5-flash',
        'gemini-3.1-flash-lite', 'gemini-2.5-flash-lite'
    ]

    instrucao_modo = (
        "Você é um especialista em debugging e correção de código. "
        "Identifique o erro de sintaxe ou lógica, corrija o código e forneça a resposta de forma extremamente direta."
        if modo_fix else
        "Você é um tutor acadêmico de programação. Forneça explicações diretas caso solicitado e, "
        "caso não tenha sido solicitada explicação, forneça apenas a resposta direta."
    )

    prompt_completo = (
        "Você é um tutor acadêmico de programação especializado em Ciência da Computação.\n"
        f"{instrucao_modo}\n\n"
        "REGRA CRÍTICA DE FORMATAÇÃO:\n"
        "Responda APENAS em texto puro (Plain Text). NÃO use nenhuma formatação Markdown (.md).\n"
        "NÃO use asteriscos para negrito (**), NÃO use blocos de código com crases (```c) e NÃO use #.\n"
        "Se houver código em C, apenas pule uma linha e escreva o código diretamente com identação normal.\n\n"
    )

    if contexto_historico:
        prompt_completo += f"CONTEXTO DE MENSAGENS ANTERIORES:\n{contexto_historico}\n---------\n"

    prompt_completo += f"SOLICITAÇÃO ATUAL: {pergunta}"

    for modelo in modelos_fallback:
        try:
            print(f"[IA] Tentando modelo: {modelo}...")
            response = client.models.generate_content(model=modelo, contents=prompt_completo)
            print(f"[IA] ✨ Sucesso com: {modelo}")
            return _sanitizar_resposta(response.text)
        except Exception as e:
            print(f"⚠️ {modelo} falhou: {e}")
            continue

    return "Desculpe, a cota gratuita de todos os modelos foi excedida. 🤖"


def _sanitizar_resposta(texto: str) -> str:
    """
    Converte #include <header.h> → #include [header.h] nas respostas da IA,
    para evitar que o navegador interprete os <> como tags HTML.
    """
    return re.sub(r'#include\s*<([^>]+)>', r'#include [\1]', texto)


# ─────────────────────────────────────────────
#  AJUDA
# ─────────────────────────────────────────────

def obter_ajuda() -> str:
    return (
        "📋 GUIA DE COMANDOS DO BOT ACADÊMICO:\n\n"
        "1. COMANDOS DE IA:\n"
        "   !chat <pergunta>  -> Pergunta normal para a IA.\n"
        "   !fix <código>     -> Correção direta de bugs no código.\n"
        "   !help             -> Exibe este menu.\n\n"
        "2. CONTEXTO POR QUANTIDADE:\n"
        "   !chatN <pergunta> -> Puxa as últimas N interações do banco.\n"
        "   Exemplo: !chat3 por que o ponteiro falhou?\n\n"
        "3. CONTEXTO CIRÚRGICO POR ID:\n"
        "   !chatid<regras> <pergunta>\n"
        "   Sintaxes de regra (separe por vírgula):\n"
        "     IDt -> Envia pergunta E resposta do ID.\n"
        "     IDm -> Envia APENAS a pergunta do ID.\n"
        "     IDr -> Envia APENAS a resposta da IA do ID.\n"
        "   Exemplo: !chatid8t,9m,10r qual a relação entre eles?\n\n"
        "4. EXECUÇÃO DE CÓDIGO C:\n"
        "   !run <código C>   -> Compila e executa o código.\n"
        "   !r <valor>        -> Envia input para o programa em execução.\n"
        "   !kill             -> Encerra o programa e entrega toda a saída acumulada.\n"
        "   A saída é entregue automaticamente após 5s sem output,\n"
        "   ou imediatamente ao usar !kill."
    )


# ─────────────────────────────────────────────
#  HELPER: prefixo com resultado pendente
# ─────────────────────────────────────────────

def _prefixo_pendente() -> str | None:
    """
    Verifica se há saída do programa C aguardando entrega.
    Retorna a string do resultado ou None.
    """
    return run.verificar_resultado_pendente()


def _juntar(pendente: str | None, msg: str) -> str:
    """Combina resultado pendente + mensagem, com separador apenas quando ambos existem."""
    if pendente:
        return f"{pendente}\n{'─' * 40}\n{msg}"
    return msg


# ─────────────────────────────────────────────
#  ROTA PRINCIPAL
# ─────────────────────────────────────────────

@app.route('/check_and_save', methods=['POST'])
def check_and_save():
    data   = request.json
    msg_id = data.get('id')
    texto  = data.get('texto', '').strip()

    cursor = db_conn.cursor()
    try:
        # Bloqueia duplicidade
        cursor.execute(
            "INSERT INTO mensagens_usuario (id, texto) VALUES (?, ?) ON CONFLICT (id) DO NOTHING",
            (msg_id, texto)
        )
        if cursor.rowcount == 0:
            return jsonify({"status": "duplicate"}), 200

        # ── !help ────────────────────────────────────────────────────────────
        if texto.startswith('!help'):
            pendente = _prefixo_pendente()
            return jsonify({"status": "new", "is_command": True,
                            "resposta": _juntar(pendente, obter_ajuda())}), 200

        # ── !run ─────────────────────────────────────────────────────────────
        if texto.startswith('!run'):
            codigo = texto[4:].strip()
            if not codigo:
                return jsonify({"status": "new", "is_command": True,
                                "resposta": "❌ Envie o código após !run. Exemplo: !run int main(){...}"}), 200
            # !run mata processo anterior e inicia novo — não há pendente útil aqui
            run.verificar_resultado_pendente()   # descarta silenciosamente
            resultado = run.compilar_e_executar(codigo)
            return jsonify({"status": "new", "is_command": True, "resposta": resultado}), 200

        # ── !r (input para programa rodando) ─────────────────────────────────
        if texto.startswith('!r ') or texto == '!r':
            pendente = _prefixo_pendente()
            valor = texto[2:].strip()
            if not valor:
                return jsonify({"status": "new", "is_command": True,
                                "resposta": _juntar(pendente, "❌ Envie o valor após !r. Exemplo: !r 42")}), 200
            resultado = run.enviar_input(valor)
            # Se programa já encerrou e tinha saída pendente, entrega só a saída (sem status de input)
            if pendente and ("encerrou" in resultado or "Nenhum programa" in resultado):
                return jsonify({"status": "new", "is_command": True, "resposta": pendente}), 200
            return jsonify({"status": "new", "is_command": True,
                            "resposta": _juntar(pendente, resultado)}), 200

        # ── !kill ─────────────────────────────────────────────────────────────
        if texto == '!kill':
            resultado = run.matar_processo()
            return jsonify({"status": "new", "is_command": True, "resposta": resultado}), 200

        # ── !s / !n (confirmação de contexto parcial) ─────────────────────────
        if texto in ['!s', '!n']:
            pendente = _prefixo_pendente()
            estado = cursor.execute(
                "SELECT msg_id, texto_original, contexto_acumulado FROM estado_pendente WHERE id_sessao = 1"
            ).fetchone()

            if not estado:
                return jsonify({"status": "new", "is_command": True,
                                "resposta": _juntar(pendente, "Não há nenhuma ação aguardando confirmação no momento.")}), 200

            orig_msg_id, texto_original, contexto_acumulado = estado
            cursor.execute("DELETE FROM estado_pendente WHERE id_sessao = 1")

            if texto == '!n':
                return jsonify({"status": "new", "is_command": True,
                                "resposta": _juntar(pendente, "Operação cancelada.")}), 200

            modo_fix      = texto_original.startswith('!fix')
            pergunta_limpa = re.sub(r'^!(chat\d*|chatid[^\s]*|fix)', '', texto_original).strip()

            resposta_ia = pedir_ao_gemini(pergunta_limpa, contexto_historico=contexto_acumulado, modo_fix=modo_fix)
            cursor.execute(
                "INSERT INTO respostas_ia (id, msg_usuario_id, texto_resposta, status) VALUES (?, ?, ?, 'sucesso')",
                (f"r_{orig_msg_id}", orig_msg_id, resposta_ia)
            )
            return jsonify({"status": "new", "is_command": True,
                            "resposta": _juntar(pendente, f"{resposta_ia}\n\nID: {orig_msg_id}")}), 200

        # ── Parsing dos comandos de IA ─────────────────────────────────────────
        is_chat_num    = re.match(r'^!chat(\d+)', texto)
        is_chat_id     = texto.startswith('!chatid')
        is_fix         = texto.startswith('!fix')
        is_chat_normal = texto.startswith('!chat') and not is_chat_num and not is_chat_id

        if is_chat_normal or is_fix or is_chat_num or is_chat_id:
            pendente = _prefixo_pendente()
            contexto_pronto = ""

            # CASO A: !chatN – contexto por quantidade
            if is_chat_num:
                limite         = int(is_chat_num.group(1))
                pergunta_limpa = texto.replace(is_chat_num.group(0), '').strip()

                historico = cursor.execute("""
                    SELECT u.id, u.texto, r.texto_resposta
                    FROM mensagens_usuario u
                    JOIN respostas_ia r ON u.id = r.msg_usuario_id
                    WHERE (u.texto LIKE '!chat%' OR u.texto LIKE '!fix%')
                      AND r.status = 'sucesso'
                    ORDER BY u.data_envio DESC
                    LIMIT ?
                """, (limite,)).fetchall()

                qtd = len(historico)
                for h_id, h_user, h_ia in reversed(historico):
                    contexto_pronto += f"[Usuário ID {h_id}]: {h_user}\n[IA]: {h_ia}\n\n"

                if qtd < limite:
                    cursor.execute("""
                        INSERT INTO estado_pendente (id_sessao, msg_id, texto_original, contexto_acumulado)
                        VALUES (1, ?, ?, ?)
                        ON CONFLICT (id_sessao) DO UPDATE
                        SET msg_id=excluded.msg_id,
                            texto_original=excluded.texto_original,
                            contexto_acumulado=excluded.contexto_acumulado
                    """, (msg_id, texto, contexto_pronto))
                    aviso = (
                        f"⚠️ Só foi possível localizar {qtd} interação(ões) com resposta válida "
                        f"(você pediu {limite}). Deseja prosseguir mesmo assim?\n"
                        "Responda !s para SIM ou !n para NÃO."
                    )
                    return jsonify({"status": "new", "is_command": True,
                                    "resposta": _juntar(pendente, aviso)}), 200

            # CASO B: !chatid – contexto cirúrgico
            elif is_chat_id:
                match_regra    = re.match(r'^!chatid([^\s]+)', texto)
                regras_str     = match_regra.group(1)
                pergunta_limpa = texto.replace(match_regra.group(0), '').strip()

                regras        = regras_str.split(',')
                falhas        = []
                contexto_temp = ""

                for regra in regras:
                    regra = regra.strip()
                    if not regra:
                        continue

                    m = re.match(r'^(.+?)([tmr])$', regra)
                    if not m:
                        falhas.append(f"'{regra}' (formato inválido, use IDt / IDm / IDr)")
                        continue

                    target_id, tipo = m.group(1), m.group(2)

                    dados = cursor.execute("""
                        SELECT u.texto, r.texto_resposta, r.status
                        FROM mensagens_usuario u
                        LEFT JOIN respostas_ia r ON u.id = r.msg_usuario_id
                        WHERE u.id = ?
                    """, (target_id,)).fetchone()

                    if not dados:
                        falhas.append(f"ID {target_id} (não encontrado no banco)")
                        continue

                    u_txt, r_txt, r_status = dados

                    if tipo in ('t', 'r'):
                        if r_txt is None or r_txt.strip() == "":
                            falhas.append(f"ID {target_id} (resposta da IA está vazia)")
                            continue
                        if r_status and r_status != 'sucesso':
                            falhas.append(f"ID {target_id} (resposta marcada como '{r_status}')")
                            continue

                    if tipo == 't':
                        contexto_temp += f"[Histórico ID {target_id} - Msg]: {u_txt}\n[Histórico ID {target_id} - Resp]: {r_txt}\n\n"
                    elif tipo == 'm':
                        contexto_temp += f"[Histórico ID {target_id} - Msg]: {u_txt}\n\n"
                    elif tipo == 'r':
                        contexto_temp += f"[Histórico ID {target_id} - Resp]: {r_txt}\n\n"

                if falhas:
                    msg_erro = (
                        "⚠️ Erro de Integridade — os seguintes IDs não puderam ser incluídos no contexto:\n"
                        + "\n".join(f"  • {f}" for f in falhas)
                        + "\n\nA operação foi abortada. Corrija as regras e tente novamente."
                    )
                    return jsonify({"status": "new", "is_command": True,
                                    "resposta": _juntar(pendente, msg_erro)}), 200

                contexto_pronto = contexto_temp

            # CASO C: !chat simples ou !fix
            else:
                cmd            = '!fix' if is_fix else '!chat'
                pergunta_limpa = texto.replace(cmd, '').strip()

            if not pergunta_limpa:
                return jsonify({"status": "new", "is_command": True,
                                "resposta": _juntar(pendente, "Digite sua dúvida ou código após o comando.")}), 200

            resposta_ia = pedir_ao_gemini(pergunta_limpa, contexto_historico=contexto_pronto, modo_fix=is_fix)
            cursor.execute(
                "INSERT INTO respostas_ia (id, msg_usuario_id, texto_resposta, status) VALUES (?, ?, ?, 'sucesso')",
                (f"r_{msg_id}", msg_id, resposta_ia)
            )
            return jsonify({"status": "new", "is_command": True,
                            "resposta": _juntar(pendente, f"{resposta_ia}\n\nID: {msg_id}")}), 200

        # ── Mensagem normal (sem comando) ──────────────────────────────────────
        # Aproveita para entregar resultado pendente se houver
        pendente = _prefixo_pendente()
        if pendente:
            return jsonify({"status": "new", "is_command": True, "resposta": pendente}), 200

        return jsonify({"status": "new", "is_command": False}), 200

    except Exception as e:
        print(f"[Erro no Servidor]: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()


if __name__ == '__main__':
    print("Servidor v4 (DuckDB + Gemini + Run com timer de silêncio) ativo na porta 5000.")
    app.run(port=5000, threaded=True)
