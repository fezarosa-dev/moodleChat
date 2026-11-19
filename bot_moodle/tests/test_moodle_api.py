"""Moodle pela API: conversão do HTML, detecção de código comido e o ciclo de leitura."""

import time
from types import SimpleNamespace as NS

from bot_moodle import moodle_api


def test_texto_e_codigo_comido():
    plano = '<p>!fix #include &lt;stdio.h&gt;<br>\nint main(void) {<br>\n\xa0 \xa0 if (a&lt;b &amp;&amp; c&gt;d) puts("x");<br>\n}</p>'
    assert moodle_api.texto(plano) == '!fix #include <stdio.h>\nint main(void) {\n    if (a<b && c>d) puts("x");\n}'
    assert not moodle_api.comido(plano)
    # o que o site entrega quando você digita esse código direto no Moodle
    assert moodle_api.comido('<p>!fix #include  int main(void) {<br>\n}</p>')
    assert moodle_api.comido('<p>!fix if (a<b>d) puts("x");</b></p>')
    assert not moodle_api.comido('<p>!chat veja <a href="https://x.y">https://x.y</a></p>')


def test_ciclo_so_responde_seus_comandos_novos(monkeypatch):
    agora = time.time()
    conversa = {"id": 7, "messages": [{"id": 13}]}
    msgs = [
        {"id": 10, "useridfrom": 1, "timecreated": agora, "text": "<p>!chat velho</p>"},  # já visto
        {"id": 11, "useridfrom": 2, "timecreated": agora, "text": "<p>!chat de outra pessoa</p>"},
        {"id": 12, "useridfrom": 1, "timecreated": agora, "text": "<p>só conversa</p>"},
        {"id": 13, "useridfrom": 1, "timecreated": agora, "text": "<p>!chat oi<br>\n\xa0 \xa0 x</p>"},
    ]
    enviados, posts = [], []

    def ws(funcao, **args):
        if funcao == "core_message_get_conversations":
            return {"conversations": [conversa]}
        if funcao == "core_message_get_conversation_messages":
            return {"messages": list(reversed(msgs))}
        assert funcao == "core_message_send_messages_to_conversation"
        enviados.append(args)
        return [{"id": 100 + len(enviados)}]

    def post(_rota, json):
        posts.append(json)
        return NS(json={"status": "new", "is_command": True, "resposta": "resposta <ok>"})

    monkeypatch.setattr(moodle_api, "ws", ws)
    visto, pular = {7: 10}, set()
    moodle_api._ciclo(NS(post=post), 1, visto, pular, agora)
    assert posts == [{"id": "13", "texto": "!chat oi\n    x"}]
    assert enviados == [{"conversationid": 7,
                         "messages": [{"text": "resposta <ok>", "textformat": 2}]}]
    assert visto == {7: 13} and 101 in pular

    # a resposta do bot chega como mensagem sua: não é reprocessada
    conversa["messages"] = [{"id": 101}]
    msgs.append({"id": 101, "useridfrom": 1, "timecreated": agora, "text": "<p>!resposta</p>"})
    moodle_api._ciclo(NS(post=post), 1, visto, pular, agora)
    assert len(posts) == 1


def test_codigo_comido_avisa_sem_chamar_a_ia(monkeypatch):
    agora = time.time()
    enviados = []

    def ws(funcao, **args):
        if funcao == "core_message_get_conversations":
            return {"conversations": [{"id": 7, "messages": [{"id": 5}]}]}
        if funcao == "core_message_get_conversation_messages":
            return {"messages": [{"id": 5, "useridfrom": 1, "timecreated": agora,
                                  "text": "<p>!fix #include  int main</p>"}]}
        enviados.append(args["messages"][0]["text"])
        return [{"id": 6}]

    monkeypatch.setattr(moodle_api, "ws", ws)
    moodle_api._ciclo(NS(post=lambda *a, **k: 1 / 0), 1, {}, set(), agora)
    assert len(enviados) == 1 and "apagou trechos" in enviados[0]
