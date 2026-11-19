"""Checagens do start.sh / start.bat que dependem das preferências: `python -m bot_moodle.checagens`.

Imprime uma linha por item, começando pelo status (OK, AVISO, PULA, ERRO ou DICA);
o script desenha cada uma e trata ERRO como impeditivo.
"""

import os
import socket
import sys
import time

from dotenv import load_dotenv


def _linha(status: str, msg: str) -> None:
    print(f"{status} {' '.join(msg.split())}", flush=True)  # uma linha só


def ias() -> None:
    """Mensagem de teste para cada IA da linha (uma vez por IA). Basta uma responder."""
    from bot_moodle.core import ai  # pylint: disable=import-outside-toplevel
    from bot_moodle.preferencias import AJUSTES, IAS, lista, pref  # pylint: disable=import-outside-toplevel

    nomes = [n for n in lista("BOT_IAS") if n in IAS]
    cliente = ai.criar_cliente(os.getenv("API_KEY", "").replace("sua_chave_aqui", ""))
    respondeu = False
    for nome in nomes:
        config = ", ".join(pref(a) for a in AJUSTES[nome])
        try:
            texto, estado = ai.chamar(nome, cliente, "Responda apenas: ok")
            if not texto:
                raise RuntimeError("resposta vazia")
        except Exception as exc:  # pylint: disable=broad-exception-caught
            erro = str(exc).splitlines()[0][:200] if str(exc) else repr(exc)
            _linha("AVISO", f"{IAS[nome]} ({config}) não respondeu ao teste: {erro}"
                            " (continua na linha: é tentada de novo a cada mensagem)")
            continue
        respondeu = True
        usado = (estado or {}).get("modelo")
        extra = f"; respondeu com {usado}" if usado and usado != pref("BOT_GEMINI_MODELO") else ""
        _linha("OK", f"{IAS[nome]} responde ({config}{extra})")
    if not nomes:
        _linha("ERRO", "Nenhuma IA escolhida")
        _linha("DICA", "rode ./start.sh --config e monte a linha de IAs")
    elif not respondeu:
        _linha("ERRO", "Nenhuma IA da linha respondeu ao teste: é preciso pelo menos uma")
        _linha("DICA", "veja os avisos acima ou mude a linha com ./start.sh --config")


def instagram() -> None:
    """Confere o .env, loga e acha a conta da DM. A sessão fica salva em ig_session.json
    e o bot a reaproveita ao subir, então não há um segundo login com senha."""
    from bot_moodle import instagram as ig  # pylint: disable=import-outside-toplevel

    falta = ig.faltando()
    if falta:
        _linha("AVISO", f"Instagram escolhido nas preferências, mas falta {', '.join(falta)} no .env"
                        " (sobe sem ele)")
        _linha("DICA", "preencha o .env (veja o README) ou tire o Instagram com ./start.sh --config")
        return
    alvo = os.environ["IG_THREAD"].lstrip("@")
    modo = "sessionid" if os.getenv("IG_SESSIONID") else "senha"
    try:
        cl = ig.login()
        cl.user_id_from_username(alvo)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _linha("AVISO", f"Instagram não logou (por {modo}): {exc!r}{ig.causa(exc)}"[:400])
        return
    _linha("OK", f"Instagram logado como @{cl.username} (por {modo}), DM com @{alvo}")


def moodle_api() -> None:
    """Testa a chave do Moodle (MOODLE_TOKEN) e as funções de mensagem que o bot usa."""
    from bot_moodle import moodle_api as mapi  # pylint: disable=import-outside-toplevel

    falta = mapi.faltando()
    url = os.getenv("MOODLE_URL", "https://moodle.unifei.edu.br").rstrip("/")
    if falta:
        _linha("AVISO", f"Moodle pela API escolhido, mas falta {', '.join(falta)} no .env (sobe sem ele)")
        _linha("DICA", mapi.COMO_RENOVAR.format(url=url))
        return
    try:
        try:
            info = mapi.ws("core_webservice_get_site_info")
        except OSError:  # rede instável (ex.: connection reset): uma segunda tentativa
            time.sleep(2)
            info = mapi.ws("core_webservice_get_site_info")
    except mapi.ChaveInvalida as exc:
        _linha("AVISO", f"Moodle: a chave (MOODLE_TOKEN) não vale mais: {exc} (sobe sem ele)")
        _linha("DICA", mapi.COMO_RENOVAR.format(url=url))
        return
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _linha("AVISO", f"Moodle (API) não respondeu: {exc!r} (o bot tenta de novo a cada 30 s"
                        " depois de subir)"[:400])
        return
    liberadas = {f["name"] for f in info["functions"]}
    faltam = [f for f in mapi.FUNCOES if f not in liberadas]
    if faltam:
        _linha("AVISO", f"Moodle: a chave não libera {', '.join(faltam)} (sobe sem ele)")
        _linha("DICA", "use o modo extensão com ./start.sh --config")
        return
    _linha("OK", f"Moodle pela API como {info['fullname']} (sem extensão)")


def porta() -> None:
    """A porta do servidor da extensão precisa estar livre."""
    numero = int(os.getenv("PORT", "5000"))
    try:
        socket.create_server(("127.0.0.1", numero)).close()
    except OSError:
        _linha("ERRO", f"Porta {numero} já está em uso (o bot já está rodando?)")
        if sys.platform == "darwin" and numero == 5000:
            _linha("DICA", "no macOS o Receptor AirPlay usa a 5000: desligue em Ajustes do Sistema"
                           " > Geral > AirDrop e Handoff")
        _linha("DICA", "feche o outro processo ou mude PORT no .env")
        return
    _linha("OK", f"Porta {numero} livre")
    if numero != 5000:
        _linha("AVISO", "A extensão espera a porta 5000 (BACKEND_URL em chatUsage.js)")


def main() -> None:
    """Roda as checagens do que foi escolhido nas preferências."""
    load_dotenv()
    from bot_moodle.preferencias import lista, pref  # pylint: disable=import-outside-toplevel

    plats = lista("BOT_PLATAFORMAS")
    try:
        ias()
        if "instagram" in plats:
            instagram()
        else:
            _linha("PULA", "Instagram desligado nas preferências")
        if "moodle" in plats and pref("BOT_MOODLE_MODO") == "api":
            moodle_api()
        elif "moodle" in plats:
            porta()
        else:
            _linha("PULA", "Moodle desligado nas preferências (não abre porta)")
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _linha("ERRO", f"as checagens quebraram: {exc!r}")
        sys.exit(1)


if __name__ == "__main__":
    main()
