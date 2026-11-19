"""As checagens do start.sh / start.bat: `python -m bot_moodle.inicio.checagens`.

Testa só o que foi escolhido no menu: cada IA da linha, o login do Instagram, a chave do Moodle
(modo API) ou a porta livre (modo extensão). Imprime uma linha por item, começando pelo status
(OK, AVISO, PULA, ERRO ou DICA); o script desenha cada uma e trata ERRO como impeditivo.
"""

import os
import sys
import time

from dotenv import load_dotenv

from bot_moodle import caminhos, ia
from bot_moodle.app import Escolhas
from bot_moodle.inicio.preferencias import AJUSTES, IAS, lista, pref
from bot_moodle.plataformas import extensao, instagram as ig
from bot_moodle.plataformas import moodle

PROMPT_DE_TESTE = "Responda apenas: ok"


def _linha(status: str, mensagem: str) -> None:
    print(f"{status} {' '.join(mensagem.split())}", flush=True)  # sempre uma linha só


def _primeira_linha(exc: Exception) -> str:
    return str(exc).splitlines()[0][:200] if str(exc) else repr(exc)


# ── IAs ──────────────────────────────────────────────────────────────────────

def _testar_ia(nome: str, cliente) -> bool:
    """Manda a mensagem de teste para uma IA e mostra o resultado; True se ela respondeu."""
    config = ", ".join(pref(ajuste) for ajuste in AJUSTES[nome])
    try:
        texto, estado = ia.chamar(nome, cliente, PROMPT_DE_TESTE)
        if not texto:
            raise RuntimeError("resposta vazia")
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _linha("AVISO", f"{IAS[nome]} ({config}) não respondeu ao teste: {_primeira_linha(exc)}"
                        " (continua na linha: é tentada de novo a cada mensagem)")
        return False
    modelo = (estado or {}).get("modelo")
    outro_modelo = f"; respondeu com {modelo}" if modelo and modelo != pref("BOT_GEMINI_MODELO") else ""
    _linha("OK", f"{IAS[nome]} responde ({config}{outro_modelo})")
    return True


def ias() -> None:
    """Uma mensagem de teste para cada IA da linha (uma vez por IA). Basta uma responder."""
    nomes = [nome for nome in lista("BOT_IAS") if nome in IAS]
    if not nomes:
        _linha("ERRO", "Nenhuma IA escolhida")
        _linha("DICA", "rode ./start.sh --config e monte a linha de IAs")
        return
    cliente = ia.criar_cliente(os.getenv("API_KEY", "").replace("sua_chave_aqui", ""))
    respostas = [_testar_ia(nome, cliente) for nome in nomes]  # testa todas, mesmo após um OK
    if not any(respostas):
        _linha("ERRO", "Nenhuma IA da linha respondeu ao teste: é preciso pelo menos uma")
        _linha("DICA", "veja os avisos acima ou mude a linha com ./start.sh --config")


# ── Instagram ────────────────────────────────────────────────────────────────

def instagram() -> None:
    """Confere o .env, loga (na ordem de BOT_IG_LOGIN) e acha a conta da DM. A sessão fica salva
    em dados/ig_session.json e o bot a reaproveita ao subir: não há um segundo login com senha."""
    falta = ig.faltando()
    if falta:
        _linha("AVISO", f"Instagram escolhido nas preferências, mas falta {', '.join(falta)} no .env"
                        " (sobe sem ele)")
        _linha("DICA", "rode ./start.sh --config e preencha a conta do Instagram")
        return
    alvo = os.environ["IG_THREAD"].lstrip("@")
    try:
        entrada = ig.entrar()
        entrada.cliente.user_id_from_username(alvo)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _linha("AVISO", f"Instagram não logou: {exc}"[:400])
        _linha("DICA", "se for verificação, confirme no app do Instagram; veja o README (Instagram)")
        return
    for falha in entrada.falhas:
        _linha("AVISO", f"Instagram: o login por {falha} (foi para a reserva)"[:400])
    _linha("OK", f"Instagram logado como @{entrada.cliente.username} (por {entrada.jeito}), DM com @{alvo}")


# ── Moodle ───────────────────────────────────────────────────────────────────

def _info_do_moodle() -> dict:
    """Os dados da conta pela API; tenta duas vezes se a rede falhar (ex.: connection reset)."""
    try:
        return moodle.ws("core_webservice_get_site_info")
    except OSError:
        time.sleep(2)
        return moodle.ws("core_webservice_get_site_info")


def moodle_api(prefixo: str = "") -> bool:
    """Testa a chave do Moodle (MOODLE_TOKEN) e as funções de mensagem que o bot usa."""
    url = os.getenv("MOODLE_URL", "https://moodle.unifei.edu.br").rstrip("/")
    falta = moodle.faltando()
    if falta:
        _linha("AVISO", f"{prefixo}Moodle pela API escolhido, mas falta {', '.join(falta)} no .env")
        _linha("DICA", moodle.COMO_RENOVAR.format(url=url))
        return False
    try:
        info = _info_do_moodle()
    except moodle.ChaveInvalida as exc:
        _linha("AVISO", f"{prefixo}Moodle: a chave (MOODLE_TOKEN) não vale mais: {exc}")
        _linha("DICA", moodle.COMO_RENOVAR.format(url=url))
        return False
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _linha("AVISO", f"{prefixo}Moodle (API) não respondeu: {exc!r} (o bot tenta de novo a cada"
                        " 30 s depois de subir)"[:400])
        return False
    liberadas = {funcao["name"] for funcao in info["functions"]}
    faltam = [funcao for funcao in moodle.FUNCOES if funcao not in liberadas]
    if faltam:
        _linha("AVISO", f"{prefixo}Moodle: a chave não libera {', '.join(faltam)}")
        _linha("DICA", "use o modo extensão com ./start.sh --config")
        return False
    _linha("OK", f"{prefixo}Moodle pela API como {info['fullname']} (sem extensão)")
    return True


def porta(prefixo: str = "", obrigatoria: bool = True) -> bool:
    """Moodle pela extensão: a porta do servidor precisa estar livre."""
    numero = extensao.porta()
    if not extensao.porta_livre(numero):
        _linha("ERRO" if obrigatoria else "AVISO",
               f"{prefixo}Porta {numero} já está em uso (o bot já está rodando?)")
        if sys.platform == "darwin" and numero == extensao.PORTA_PADRAO:
            _linha("DICA", "no macOS o Receptor AirPlay usa a 5000: desligue em Ajustes do Sistema"
                           " > Geral > AirDrop e Handoff")
        _linha("DICA", "feche o outro processo ou mude PORT no .env")
        return False
    _linha("OK", f"{prefixo}Porta {numero} livre para a extensão")
    if numero != extensao.PORTA_PADRAO:
        _linha("AVISO", "A extensão espera a porta 5000 (BACKEND_URL em extensao/chatUsage.js)")
    return True


def moodle_em_ordem(modos: tuple) -> None:
    """Testa cada jeito de conectar no Moodle, na ordem: o primeiro que funcionar é o usado."""
    funcionam = []
    for i, modo in enumerate(modos):
        prefixo = "Reserva: " if i else ""
        teste = moodle_api(prefixo) if modo == "api" else porta(prefixo, obrigatoria=len(modos) == 1)
        funcionam.append(teste)
    if len(modos) > 1 and not any(funcionam):
        _linha("AVISO", "Moodle: nenhum jeito de conectar funcionou (sobe sem ele)")


# ── o plano ──────────────────────────────────────────────────────────────────

def _pula(mensagem: str):
    return lambda: _linha("PULA", mensagem)


def _etapas(escolhas: Escolhas) -> list:
    """O que checar, na ordem, conforme as escolhas do menu."""
    return [
        ias,
        instagram if escolhas.instagram else _pula("Instagram desligado nas preferências"),
        (lambda: moodle_em_ordem(escolhas.moodle)) if escolhas.moodle
        else _pula("Moodle desligado nas preferências (não abre porta)"),
    ]


def main() -> None:
    """Roda as checagens do que foi escolhido nas preferências."""
    load_dotenv(caminhos.ENV)
    try:
        for etapa in _etapas(Escolhas.das_preferencias()):
            etapa()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _linha("ERRO", f"as checagens quebraram: {exc!r}")
        sys.exit(1)


if __name__ == "__main__":
    main()
