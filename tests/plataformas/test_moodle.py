"""Moodle pela API: a chave, as chamadas, o texto das mensagens e o ciclo de leitura (API falsa)."""

import base64
import io
import json
import time
from types import SimpleNamespace as NS

import pytest

from bot_moodle.plataformas import moodle

PLANO = ('<p>!fix #include &lt;stdio.h&gt;<br>\nint main(void) {<br>\n\xa0 \xa0 '
         'if (a&lt;b &amp;&amp; c&gt;d) puts("x");<br>\n}</p>')


# ── a chave e as chamadas ────────────────────────────────────────────────────

def test_chave_aceita_o_token_puro(monkeypatch):
    monkeypatch.setenv("MOODLE_TOKEN", " abc123 ")
    assert moodle.chave() == "abc123"


def test_chave_aceita_o_moodlemobile_inteiro(monkeypatch):
    codificado = base64.b64encode(b"assinatura:::meu_token").decode()
    monkeypatch.setenv("MOODLE_TOKEN", f"moodlemobile://token={codificado}")
    assert moodle.chave() == "meu_token"


@pytest.fixture(name="servidor")
def fixture_servidor(monkeypatch):
    """O urlopen falso: guarda o que foi enviado e devolve `servidor.resposta` em JSON."""
    servidor = NS(resposta={}, enviado=None)

    def urlopen(url, dados, **_kwargs):
        servidor.url, servidor.enviado = url, dados.decode()
        return io.BytesIO(json.dumps(servidor.resposta).encode())

    monkeypatch.setattr(moodle.urllib.request, "urlopen", urlopen)
    monkeypatch.setenv("MOODLE_URL", "https://moodle.exemplo.br/")
    monkeypatch.setenv("MOODLE_TOKEN", "abc")
    return servidor


def test_ws_manda_listas_no_formato_do_moodle(servidor):
    moodle.ws("core_message_send_messages_to_conversation", conversationid=7,
              messages=[{"text": "oi", "textformat": 2}], mergeself=True)
    enviado = moodle.urllib.parse.parse_qs(servidor.enviado)
    assert servidor.url == "https://moodle.exemplo.br/webservice/rest/server.php"
    assert enviado["wstoken"] == ["abc"] and enviado["messages[0][text]"] == ["oi"]
    assert enviado["mergeself"] == ["1"]


def test_token_invalido_vira_chave_invalida(servidor):
    servidor.resposta = {"exception": "x", "errorcode": "invalidtoken", "message": "Token inválido"}
    with pytest.raises(moodle.ChaveInvalida, match="Token inválido"):
        moodle.ws("core_webservice_get_site_info")


def test_outro_erro_da_api_vira_runtime_error(servidor):
    servidor.resposta = {"exception": "x", "errorcode": "invalidparameter", "message": "parâmetro"}
    with pytest.raises(RuntimeError, match="invalidparameter"):
        moodle.ws("core_webservice_get_site_info")


def test_faltando(monkeypatch):
    monkeypatch.setenv("MOODLE_URL", "https://moodle.exemplo.br")
    assert moodle.faltando() == ["MOODLE_TOKEN"]


# ── o texto das mensagens ────────────────────────────────────────────────────

def test_texto_volta_como_foi_digitado():
    assert moodle.texto(PLANO) == '!fix #include <stdio.h>\nint main(void) {\n    if (a<b && c>d) puts("x");\n}'


def test_codigo_digitado_no_site_chega_cortado_e_e_detectado():
    assert not moodle.comido(PLANO)
    assert moodle.comido('<p>!fix #include  int main(void) {<br>\n}</p>')  # o <stdio.h> sumiu
    assert moodle.comido('<p>!fix if (a<b>d) puts("x");</b></p>')        # virou tag <b>
    assert not moodle.comido('<p>!chat veja <a href="https://x.y">https://x.y</a></p>')


# ── o ciclo de leitura ───────────────────────────────────────────────────────

@pytest.fixture(name="api")
def fixture_api(monkeypatch):
    """A API falsa: uma conversa (id 7) com as mensagens de `api.msgs`; guarda o que foi enviado."""
    api = NS(msgs=[], enviados=[], conversa={"id": 7, "messages": []})

    def ws(funcao, **args):
        if funcao == "core_message_get_conversations":
            return {"conversations": [api.conversa]}
        if funcao == "core_message_get_conversation_messages":
            return {"messages": list(reversed(api.msgs))}
        api.enviados.append(args)
        novo = {"id": 100 + len(api.enviados), "useridfrom": 1, "timecreated": time.time(),
                "text": f"<p>{args['messages'][0]['text']}</p>"}
        api.msgs.append(novo)
        return [novo]

    monkeypatch.setattr(moodle, "ws", ws)
    return api


def mensagem(api, msg_id, texto, de=1):
    api.msgs.append({"id": msg_id, "useridfrom": de, "timecreated": time.time(), "text": f"<p>{texto}</p>"})
    api.conversa["messages"] = [{"id": msg_id}]


def rota(resposta="resposta <ok>"):
    """A rota /check_and_save falsa: guarda o que recebeu e responde."""
    recebidos = []

    def post(_caminho, json):  # pylint: disable=redefined-outer-name
        recebidos.append(json)
        return NS(json={"status": "new", "is_command": True, "resposta": resposta})

    return NS(post=post, recebidos=recebidos)


def test_responde_os_seus_comandos_novos(api):
    leitura = moodle.Leitura(uid=1, visto={7: 10})
    mensagem(api, 10, "!chat velho")
    mensagem(api, 11, "!chat de outra pessoa", de=2)
    mensagem(api, 12, "só conversa")
    mensagem(api, 13, "!chat oi<br>\n\xa0 \xa0 x")
    falsa = rota()
    moodle._ciclo(falsa, leitura)  # pylint: disable=protected-access
    assert falsa.recebidos == [{"id": "13", "texto": "!chat oi\n    x"}]
    assert api.enviados == [{"conversationid": 7, "messages": [{"text": "resposta <ok>", "textformat": 2}]}]
    assert leitura.visto == {7: 13}


def test_a_resposta_do_bot_nao_e_reprocessada(api):
    leitura = moodle.Leitura(uid=1)
    mensagem(api, 13, "!chat oi")
    falsa = rota(resposta="!isso parece comando")
    moodle._ciclo(falsa, leitura)  # pylint: disable=protected-access
    api.conversa["messages"] = [{"id": api.msgs[-1]["id"]}]
    moodle._ciclo(falsa, leitura)  # pylint: disable=protected-access
    assert len(falsa.recebidos) == 1


def test_conversa_sem_novidade_nem_e_buscada(api, monkeypatch):
    leitura = moodle.Leitura(uid=1, visto={7: 13})
    mensagem(api, 13, "!chat oi")
    monkeypatch.setattr(moodle, "_mensagens", lambda *_: pytest.fail("não devia buscar"))
    moodle._ciclo(rota(), leitura)  # pylint: disable=protected-access


def test_comando_antigo_de_antes_do_bot_subir_e_ignorado(api):
    leitura = moodle.Leitura(uid=1, inicio=time.time() + 10 * moodle.TOLERANCIA_S)
    mensagem(api, 13, "!chat de ontem")
    falsa = rota()
    moodle._ciclo(falsa, leitura)  # pylint: disable=protected-access
    assert not falsa.recebidos


def test_codigo_cortado_avisa_sem_chamar_a_ia(api):
    mensagem(api, 5, "!fix #include  int main")
    falsa = rota()
    moodle._ciclo(falsa, moodle.Leitura(uid=1))  # pylint: disable=protected-access
    assert not falsa.recebidos and "apagou trechos" in api.enviados[0]["messages"][0]["text"]


def test_resposta_longa_vai_em_partes(api):
    mensagem(api, 5, "!chat conta uma história")
    moodle._ciclo(rota(resposta="palavra " * 1000), moodle.Leitura(uid=1))  # pylint: disable=protected-access
    textos = [envio["messages"][0]["text"] for envio in api.enviados]
    assert len(textos) == 3 and textos[0].startswith("(1/3) ")


def test_chave_invalida_ao_subir_nao_sobe_para_a_reserva_assumir(monkeypatch):
    monkeypatch.setenv("MOODLE_URL", "https://moodle.exemplo.br")

    def ws(_funcao, **_args):
        raise moodle.ChaveInvalida("Token inválido")

    monkeypatch.setattr(moodle, "ws", ws)
    assert moodle._conectar("https://moodle.exemplo.br") is None  # pylint: disable=protected-access


def test_sem_chave_nao_sobe(monkeypatch):
    monkeypatch.setenv("MOODLE_URL", "https://moodle.exemplo.br")
    assert moodle.iniciar(app=None) is None
