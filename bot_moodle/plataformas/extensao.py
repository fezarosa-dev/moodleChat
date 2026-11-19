"""Moodle pela extensão do navegador: um servidor local na porta 5000 recebe as mensagens.

A extensão (pasta extensao/) lê o chat aberto no navegador e manda cada mensagem para
/check_and_save; a resposta volta para ela escrever no chat.
"""

import os
import socket
import threading

from werkzeug.serving import make_server

PORTA_PADRAO = 5000


def porta() -> int:
    """A porta do servidor (PORT no .env; a extensão espera a 5000)."""
    return int(os.getenv("PORT", str(PORTA_PADRAO)))


def porta_livre(numero: int) -> bool:
    """Ninguém está usando a porta (ex.: outro bot rodando)."""
    try:
        socket.create_server(("127.0.0.1", numero)).close()
    except OSError:
        return False
    return True


def iniciar(app) -> "threading.Thread | None":
    """Sobe o servidor numa thread; None se a porta estiver ocupada (a reserva assume)."""
    # confere antes: com a porta ocupada, o servidor do werkzeug encerra o programa todo
    if not porta_livre(porta()):
        print(f"\n⚠️ Moodle pela extensão desligado: a porta {porta()} está ocupada.\n")
        return None
    servidor = make_server("127.0.0.1", porta(), app, threaded=True)
    print(f"🧩 Moodle pela extensão: servidor na porta {porta()} (abra o chat no navegador).")
    thread = threading.Thread(target=servidor.serve_forever, daemon=True, name="extensao")
    thread.start()
    return thread
