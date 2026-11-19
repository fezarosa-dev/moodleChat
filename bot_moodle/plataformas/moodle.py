"""Moodle pela API oficial (os web services do app Moodle), sem extensão.

A cada INTERVALO segundos olha as suas conversas mais recentes, manda cada comando ("!...") que
VOCÊ escreveu para a rota /check_and_save e responde na mesma conversa. Precisa de MOODLE_URL e
MOODLE_TOKEN no .env (a chave do app; o README ensina a pegar).
"""

import base64
import html
import json
import os
import re
import ssl
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

import certifi

from bot_moodle import caminhos
from bot_moodle.plataformas.instagram import dividir

INTERVALO = 5             # segundos entre leituras: não pesar no servidor da UNIFEI
ESPERA_ERRO_S = 60        # rede ou servidor fora: espera antes de tentar de novo
ESPERA_CONEXAO_S = 30     # idem, ao subir
LIMITE = 3000             # o chat corta em ~4096 caracteres; folga como na extensão
CONVERSAS = 20            # quantas conversas recentes olhar (mandar uma mensagem a põe no topo)
TOLERANCIA_S = 300        # conversa que entra na lista depois de subir: só comandos recentes
VIDA = caminhos.VIDA_MOODLE  # tocado a cada leitura; o vigia confere se não parou
FUNCOES = ["core_message_get_conversations", "core_message_get_conversation_messages",
           "core_message_send_messages_to_conversation"]
COMO_RENOVAR = ("pegue outra chave: logado no Moodle, abra uma aba com F12 → Rede (Preservar"
                " registro), acesse {url}/admin/tool/mobile/launch.php?service=moodle_mobile_app"
                "&passport=12345&urlscheme=moodlemobile, copie o valor do cabeçalho location da"
                " linha launch.php e cole no .env como MOODLE_TOKEN=moodlemobile://token=…")
FORMATO_TEXTO = 2         # FORMAT_PLAIN: o Moodle guarda < > & e a indentação como estão
# o site envia em FORMAT_MOODLE, que trata "<...>" como HTML: outras tags não foram digitadas assim
TAGS_DO_MOODLE = {"p", "br", "a", "img", "span", "div"}
AVISO_CODIGO_CORTADO = ("⚠️ O Moodle apagou trechos entre < > da sua mensagem (o site trata como"
                        " HTML), então não mandei para a IA. Reenvie trocando < por &lt; e > por"
                        " &gt;, ou mande pelo Instagram.")
# certificados do certifi (já vem com o requests): o Python do python.org no macOS não acha os do sistema
SSL = ssl.create_default_context(cafile=certifi.where())


class ChaveInvalida(RuntimeError):
    """MOODLE_TOKEN vencido ou revogado."""


# ── a API ────────────────────────────────────────────────────────────────────

def chave() -> str:
    """O token do .env; aceita também o moodlemobile://token=… inteiro, como sai do navegador."""
    bruto = os.environ["MOODLE_TOKEN"].strip()
    if not bruto.startswith("moodlemobile://token="):
        return bruto
    # base64 de "assinatura_do_site:::token[:::token_privado]"
    return base64.b64decode(bruto.split("=", 1)[1]).decode().split(":::")[1]


def _achatar(nome: str, valor, dados: dict) -> None:
    """Listas e dicts no formato do Moodle: messages[0][text]=..."""
    if isinstance(valor, dict):
        for chave_interna, item in valor.items():
            _achatar(f"{nome}[{chave_interna}]", item, dados)
    elif isinstance(valor, list):
        for i, item in enumerate(valor):
            _achatar(f"{nome}[{i}]", item, dados)
    else:
        dados[nome] = int(valor) if isinstance(valor, bool) else valor


def ws(funcao: str, **args):
    """Chama uma função da API. Lança ChaveInvalida se o token não vale mais."""
    dados = {"wstoken": chave(), "wsfunction": funcao, "moodlewsrestformat": "json"}
    for nome, valor in args.items():
        _achatar(nome, valor, dados)
    url = os.environ["MOODLE_URL"].rstrip("/") + "/webservice/rest/server.php"
    with urllib.request.urlopen(url, urllib.parse.urlencode(dados).encode(), timeout=30,
                                context=SSL) as resposta:
        resultado = json.load(resposta)
    if not (isinstance(resultado, dict) and "exception" in resultado):
        return resultado
    if resultado.get("errorcode") in ("invalidtoken", "accessexception"):
        raise ChaveInvalida(resultado.get("message"))
    raise RuntimeError(f"{funcao}: {resultado.get('errorcode')}: {resultado.get('message')}")


# ── o texto das mensagens ────────────────────────────────────────────────────

def texto(corpo: str) -> str:
    """HTML da API -> o texto como foi digitado (quebras de linha e indentação)."""
    sem_br = re.sub(r"<br\s*/?>\n?", "\n", corpo)
    sem_paragrafos = re.sub(r"</p>\s*<p[^>]*>", "\n", sem_br)
    sem_tags = re.sub(r"<[^>]+>", "", sem_paragrafos)
    return html.unescape(sem_tags).replace("\xa0", " ").strip()


def comido(corpo: str) -> bool:
    """O site tratou parte do código como HTML e apagou (ex.: #include <stdio.h>, a<b && c>d)."""
    tags = {tag.lower() for tag in re.findall(r"</?([a-zA-Z][\w-]*)", corpo)}
    include_sem_header = re.search(r"#include(?!\s*(<|\"|&lt;|&quot;))", corpo)
    return bool(tags - TAGS_DO_MOODLE) or bool(include_sem_header)


# ── a leitura das conversas ──────────────────────────────────────────────────

@dataclass
class Leitura:
    """O que o bot sabe entre uma leitura e outra."""

    uid: int                                     # a sua conta
    visto: dict = field(default_factory=dict)    # conversa -> maior id de mensagem já olhado
    pular: set = field(default_factory=set)      # as respostas do próprio bot
    inicio: float = field(default_factory=time.time)

    def e_comando_novo(self, conversa: int, msg: dict) -> bool:
        """Mensagem sua, nova, recente e que não é resposta do bot (o "!" é conferido depois)."""
        return (msg["id"] > self.visto.get(conversa, 0)
                and msg["id"] not in self.pular
                and msg["useridfrom"] == self.uid
                and msg["timecreated"] >= self.inicio - TOLERANCIA_S)


def _conversas(uid: int) -> list[dict]:
    return ws("core_message_get_conversations", userid=uid, limitnum=CONVERSAS,
              mergeself=True)["conversations"]


def _ultima(conversa: dict) -> int:
    return max((msg["id"] for msg in conversa.get("messages") or []), default=0)


def _mensagens(uid: int, conversa: int) -> list[dict]:
    """As últimas mensagens da conversa, da mais antiga à mais nova."""
    msgs = ws("core_message_get_conversation_messages", currentuserid=uid, convid=conversa,
              limitnum=20, newest=True)["messages"]
    return sorted(msgs, key=lambda msg: msg["id"])


def _enviar(conversa: int, resposta: str, pular: set) -> int:
    partes = dividir(resposta, LIMITE)
    for parte in partes:
        enviadas = ws("core_message_send_messages_to_conversation", conversationid=conversa,
                      messages=[{"text": parte, "textformat": FORMATO_TEXTO}])
        pular.update(msg["id"] for msg in enviadas)
    return len(partes)


def _responder(rota, conversa: int, msg: dict, leitura: Leitura) -> None:
    """Manda o comando para a rota e a resposta para a conversa."""
    digitado = texto(msg["text"])
    if not digitado.startswith("!"):
        return
    leitura.pular.add(msg["id"])
    if comido(msg["text"]):
        _enviar(conversa, AVISO_CODIGO_CORTADO, leitura.pular)
        return
    atraso, inicio = time.time() - msg["timecreated"], time.monotonic()
    # o mesmo id da extensão (data-message-id): trocar de modo não responde de novo
    resposta = rota.post("/check_and_save", json={"id": str(msg["id"]), "texto": digitado}).json
    if not (resposta.get("status") == "new" and resposta.get("is_command") and resposta.get("resposta")):
        return
    ia_pronta = time.monotonic()
    partes = _enviar(conversa, resposta["resposta"], leitura.pular)
    print(f"[Moodle] {digitado.split()[0]} recebido {atraso:.0f}s após o envio · "
          f"IA {ia_pronta - inicio:.0f}s · enviado em {partes} parte(s) ({time.monotonic() - ia_pronta:.0f}s)")


def _ciclo(rota, leitura: Leitura) -> None:
    """Uma leitura: processa os comandos novos que você escreveu, do mais antigo ao mais novo."""
    for conversa in _conversas(leitura.uid):
        cid, ultima = conversa["id"], _ultima(conversa)
        if ultima <= leitura.visto.get(cid, 0):
            continue  # nada de novo nessa conversa: nem busca as mensagens
        msgs = _mensagens(leitura.uid, cid)
        for msg in msgs:
            if leitura.e_comando_novo(cid, msg):
                _responder(rota, cid, msg, leitura)
        leitura.visto[cid] = max([leitura.visto.get(cid, 0), ultima] + [msg["id"] for msg in msgs])


def _conectar(url: str) -> "Leitura | None":
    """Confere a chave e anota o que já está nas conversas (não dispara respostas ao subir).
    Rede fora: tenta de novo. Chave inválida: None (a reserva, se houver, assume)."""
    while True:
        try:
            info = ws("core_webservice_get_site_info")
            leitura = Leitura(uid=info["userid"])
            leitura.visto = {c["id"]: _ultima(c) for c in _conversas(leitura.uid)}
            print(f"🎓 Moodle (API): vigiando as conversas de {info['fullname']} (só os seus comandos !).")
            return leitura
        except ChaveInvalida as exc:
            print(f"\n⚠️ Moodle (API) desligado: {exc}\n   → {COMO_RENOVAR.format(url=url)}\n")
            return None
        except Exception as exc:  # pylint: disable=broad-exception-caught
            print(f"[Moodle] não conectou ({exc!r}); tentando de novo em {ESPERA_CONEXAO_S} s"
                  " (confira MOODLE_URL e a rede)")
            time.sleep(ESPERA_CONEXAO_S)


def _rodar(app) -> None:
    url = os.environ["MOODLE_URL"].rstrip("/")
    leitura = _conectar(url)
    rota = app.test_client()
    while leitura:
        VIDA.touch()
        try:
            _ciclo(rota, leitura)
        except ChaveInvalida as exc:
            print(f"\n⚠️ Moodle (API) parou: a chave venceu ou foi revogada ({exc}).\n"
                  f"   → {COMO_RENOVAR.format(url=url)} e reinicie o bot.\n")
            VIDA.unlink(missing_ok=True)  # parar de propósito não é travar: o vigia não reinicia
            return
        except Exception as exc:  # pylint: disable=broad-exception-caught
            print(f"[Moodle] erro: {exc!r}")
            time.sleep(ESPERA_ERRO_S)
        time.sleep(INTERVALO)


def faltando() -> list[str]:
    """Variáveis do .env que faltam."""
    return [nome for nome in ("MOODLE_URL", "MOODLE_TOKEN") if not os.getenv(nome)]


def iniciar(app) -> "threading.Thread | None":
    """Sobe a leitura das conversas numa thread; None sem a URL ou a chave (a reserva assume)."""
    VIDA.unlink(missing_ok=True)  # de uma execução anterior: o vigia só olha depois de conectar
    falta = faltando()
    if falta:
        print(f"\n⚠️ Moodle (API) desligado: falta {', '.join(falta)} no .env.\n")
        return None
    thread = threading.Thread(target=_rodar, args=(app,), daemon=True, name="moodle")
    thread.start()
    return thread
