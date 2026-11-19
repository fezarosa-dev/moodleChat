"""Moodle sem extensão: lê e responde as mensagens pela API oficial (web services do app).

Faz o papel da extensão: a cada poucos segundos olha as conversas, manda cada comando
("!...") que VOCÊ escreveu para a rota /check_and_save e responde na mesma conversa.
Precisa de MOODLE_URL e MOODLE_TOKEN no .env (a chave do app, veja o README).
"""

import html
import json
import os
import re
import ssl
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

import certifi

from bot_moodle.instagram import dividir

INTERVALO = 5             # segundos entre leituras: não pesar no servidor da UNIFEI
LIMITE = 3000             # o chat corta em ~4096 caracteres; folga como na extensão
TOLERANCIA_S = 300        # conversa que entra na lista depois de subir: só comandos recentes
VIDA = Path(".moodle_vivo")  # tocado a cada leitura; o vigia confere se não parou
FUNCOES = ["core_message_get_conversations", "core_message_get_conversation_messages",
           "core_message_send_messages_to_conversation"]
COMO_RENOVAR = ("pegue outra chave: logado no Moodle, abra uma aba com F12 → Rede (Preservar"
                " registro), acesse {url}/admin/tool/mobile/launch.php?service=moodle_mobile_app"
                "&passport=12345&urlscheme=moodlemobile, copie o valor do cabeçalho location da"
                " linha launch.php e cole no .env como MOODLE_TOKEN=moodlemobile://token=…")
FORMATO_TEXTO = 2         # FORMAT_PLAIN: o Moodle guarda < > & e a indentação como estão
# o site envia em FORMAT_MOODLE, que trata "<...>" como HTML: estas tags não foram escritas
TAGS_DO_MOODLE = {"p", "br", "a", "img", "span", "div"}
# certificados do certifi (já vem com o requests): o Python do python.org no macOS não acha os do sistema
SSL = ssl.create_default_context(cafile=certifi.where())


class ChaveInvalida(RuntimeError):
    """MOODLE_TOKEN vencido ou revogado."""


def chave() -> str:
    """O token do .env; aceita também o moodlemobile://token=… inteiro, como sai do navegador."""
    bruto = os.environ["MOODLE_TOKEN"].strip()
    if bruto.startswith("moodlemobile://token="):
        import base64  # pylint: disable=import-outside-toplevel
        bruto = base64.b64decode(bruto.split("=", 1)[1]).decode().split(":::")[1]
    return bruto


def ws(funcao: str, **args):
    """Chama uma função da API. Listas e dicts viram o formato do Moodle (a[0][b]=c)."""
    dados = {"wstoken": chave(), "wsfunction": funcao, "moodlewsrestformat": "json"}

    def achatar(nome, valor):
        if isinstance(valor, dict):
            for k, v in valor.items():
                achatar(f"{nome}[{k}]", v)
        elif isinstance(valor, list):
            for i, v in enumerate(valor):
                achatar(f"{nome}[{i}]", v)
        else:
            dados[nome] = int(valor) if isinstance(valor, bool) else valor

    for nome, valor in args.items():
        achatar(nome, valor)
    url = os.environ["MOODLE_URL"].rstrip("/") + "/webservice/rest/server.php"
    with urllib.request.urlopen(url, urllib.parse.urlencode(dados).encode(), timeout=30,
                                context=SSL) as r:
        res = json.load(r)
    if isinstance(res, dict) and "exception" in res:
        if res.get("errorcode") in ("invalidtoken", "accessexception"):
            raise ChaveInvalida(res.get("message"))
        raise RuntimeError(f"{funcao}: {res.get('errorcode')}: {res.get('message')}")
    return res


def texto(corpo: str) -> str:
    """HTML da API -> texto como foi digitado (quebras de linha e indentação)."""
    t = re.sub(r"<br\s*/?>\n?", "\n", corpo)
    t = re.sub(r"</p>\s*<p[^>]*>", "\n", t)
    t = re.sub(r"<[^>]+>", "", t)
    return html.unescape(t).replace("\xa0", " ").strip()


def comido(corpo: str) -> bool:
    """O site tratou parte do código como HTML e apagou (ex.: #include <stdio.h>, a<b && c>d)."""
    tags = {t.lower() for t in re.findall(r"</?([a-zA-Z][\w-]*)", corpo)}
    return bool(tags - TAGS_DO_MOODLE) or bool(re.search(r"#include(?!\s*(<|\"|&lt;|&quot;))", corpo))


def _enviar(conversa: int, resposta: str, pular: set) -> int:
    partes = dividir(resposta, LIMITE)
    for parte in partes:
        enviadas = ws("core_message_send_messages_to_conversation", conversationid=conversa,
                      messages=[{"text": parte, "textformat": FORMATO_TEXTO}])
        pular.update(m["id"] for m in enviadas)
    return len(partes)


def _conversas(uid: int) -> list[dict]:
    return ws("core_message_get_conversations", userid=uid, limitnum=20,
              mergeself=True)["conversations"]


def _ultima(conversa: dict) -> int:
    return max((m["id"] for m in conversa.get("messages") or []), default=0)


def _ciclo(cliente, uid: int, visto: dict, pular: set, inicio: float) -> None:
    """Uma leitura: processa os comandos novos que você escreveu, do mais antigo ao mais novo."""
    for conversa in _conversas(uid):
        cid, ultima = conversa["id"], _ultima(conversa)
        if ultima <= visto.get(cid, 0):
            continue
        msgs = ws("core_message_get_conversation_messages", currentuserid=uid, convid=cid,
                  limitnum=20, newest=True)["messages"]
        for msg in sorted(msgs, key=lambda m: m["id"]):
            if (msg["id"] <= visto.get(cid, 0) or msg["id"] in pular or msg["useridfrom"] != uid
                    or msg["timecreated"] < inicio - TOLERANCIA_S):
                continue
            digitado = texto(msg["text"])
            if not digitado.startswith("!"):
                continue
            pular.add(msg["id"])
            atraso, t0 = time.time() - msg["timecreated"], time.monotonic()
            if comido(msg["text"]):
                _enviar(cid, "⚠️ O Moodle apagou trechos entre < > da sua mensagem (o site trata"
                             " como HTML), então não mandei para a IA. Reenvie trocando < por &lt;"
                             " e > por &gt;, ou mande pelo Instagram.", pular)
                continue
            # mesmo id da extensão (data-message-id): trocar de modo não responde de novo
            resp = cliente.post("/check_and_save", json={"id": str(msg["id"]), "texto": digitado}).json
            if resp.get("status") == "new" and resp.get("is_command") and resp.get("resposta"):
                t1 = time.monotonic()
                n = _enviar(cid, resp["resposta"], pular)
                print(f"[Moodle] {digitado.split()[0]} recebido {atraso:.0f}s após o envio · "
                      f"IA {t1 - t0:.0f}s · enviado em {n} parte(s) ({time.monotonic() - t1:.0f}s)")
        visto[cid] = max([visto.get(cid, 0), ultima] + [m["id"] for m in msgs])


def _rodar(app) -> None:
    url = os.environ["MOODLE_URL"].rstrip("/")
    while True:
        try:
            info = ws("core_webservice_get_site_info")
            uid = info["userid"]
            # o que já está nas conversas ao subir não dispara respostas
            visto = {c["id"]: _ultima(c) for c in _conversas(uid)}
            break
        except ChaveInvalida as exc:
            print(f"\n⚠️ Moodle (API) desligado (o resto do bot segue funcionando): {exc}\n"
                  f"   → {COMO_RENOVAR.format(url=url)}\n")
            return
        except Exception as exc:  # pylint: disable=broad-exception-caught
            # rede caiu ou servidor fora: não desliga o Moodle por uma falha passageira
            print(f"[Moodle] não conectou ({exc!r}); tentando de novo em 30 s (confira MOODLE_URL e a rede)")
            time.sleep(30)
    print(f"🎓 Moodle (API): vigiando as conversas de {info['fullname']} (só os seus comandos !).")

    cliente, pular, inicio = app.test_client(), set(), time.time()
    while True:
        VIDA.touch()
        try:
            _ciclo(cliente, uid, visto, pular, inicio)
        except ChaveInvalida as exc:
            print(f"\n⚠️ Moodle (API) parou: a chave venceu ou foi revogada ({exc}).\n"
                  f"   → {COMO_RENOVAR.format(url=url)} e reinicie o bot.\n")
            VIDA.unlink(missing_ok=True)  # parar de propósito não é travar: o vigia não reinicia
            return
        except Exception as exc:  # pylint: disable=broad-exception-caught
            print(f"[Moodle] erro: {exc!r}")
            time.sleep(60)  # rede/servidor fora: espera antes de tentar de novo
        time.sleep(INTERVALO)


def faltando() -> list[str]:
    """Variáveis do .env que faltam."""
    return [v for v in ("MOODLE_URL", "MOODLE_TOKEN") if not os.getenv(v)]


def iniciar(app) -> "threading.Thread | None":
    """Sobe a leitura das conversas numa thread, se o .env tiver a URL e a chave."""
    VIDA.unlink(missing_ok=True)  # de uma execução anterior: o vigia só olha depois de logar
    falta = faltando()
    if falta:
        print(f"\n⚠️ Moodle (API) desligado: falta {', '.join(falta)} no .env.\n")
        return None
    thread = threading.Thread(target=_rodar, args=(app,), daemon=True, name="moodle")
    thread.start()
    return thread
