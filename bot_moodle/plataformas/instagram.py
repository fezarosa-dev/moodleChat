"""Instagram: lê a DM com IG_THREAD e responde pela conta IG_USERNAME, com os mesmos comandos do Moodle.

O login segue a ordem de BOT_IG_LOGIN: usuário e senha (com o código do 2FA gerado a partir de
IG_TOTP_SEED) e/ou o cookie sessionid do navegador. O primeiro que funcionar é usado. Usa o
instagrapi (a API privada do app): há risco de bloqueio, por isso o README recomenda uma conta
só para o bot.
"""

import os
import random
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from bot_moodle import caminhos
from bot_moodle.inicio.preferencias import lista

# a Meta documenta 1000 bytes UTF-8 por mensagem (acento = 2 bytes, emoji = 4); folga de 100
LIMITE_BYTES = 900
RESERVA_PREFIXO = 10      # espaço para "(12/34) "
INTERVALO = 4             # segundos entre leituras da DM (+ 0–2 s): mais rápido arrisca bloqueio
PAUSA_PARTES = 2.5        # segundos entre as partes de uma resposta longa (rajada parece spam)
SESSAO = caminhos.SESSAO_INSTAGRAM
VIDA = caminhos.VIDA_INSTAGRAM  # tocado a cada leitura da DM; o vigia confere se não parou
DADO_DO_LOGIN = {"senha": "IG_PASSWORD", "sessionid": "IG_SESSIONID"}  # o que cada jeito precisa


# ── mensagens ────────────────────────────────────────────────────────────────

def dividir(texto: str, limite: int = LIMITE_BYTES) -> list[str]:
    """Quebra em partes <= limite bytes, preferindo cortar em quebra de linha, depois em espaço.
    Com mais de uma parte, numera: "(1/3) ...". Mesma regra da extensão, mas contando bytes UTF-8."""
    max_bytes = limite - RESERVA_PREFIXO
    partes, resto = [], texto
    while len(resto.encode()) > max_bytes:
        # o maior pedaço que cabe em max_bytes sem partir um caractere multibyte
        cabe = len(resto.encode()[:max_bytes].decode("utf-8", "ignore"))
        corte = _onde_cortar(resto, cabe)
        partes.append(resto[:corte])
        resto = resto[corte:]
        resto = resto[1:] if resto[:1] in ("\n", " ") else resto
    partes.append(resto)
    if len(partes) == 1:
        return partes
    return [f"({i}/{len(partes)}) {parte}" for i, parte in enumerate(partes, 1)]


def _onde_cortar(texto: str, cabe: int) -> int:
    """Na última quebra de linha da metade de trás; senão no último espaço; senão no limite."""
    for separador in ("\n", " "):
        corte = texto.rfind(separador, 0, cabe)
        if corte >= cabe // 2:
            return corte
    return cabe


# ── login ────────────────────────────────────────────────────────────────────

@dataclass
class Entrada:
    """O resultado do login: o cliente, o jeito que funcionou e os que falharam antes dele."""

    cliente: Any  # o Client do instagrapi
    jeito: str
    falhas: list[str] = field(default_factory=list)


def _com_senha(cliente, usuario: str) -> None:
    # com 2FA por app autenticador: o bot gera o código de 6 dígitos sozinho
    semente = os.getenv("IG_TOTP_SEED", "").replace(" ", "").upper()
    codigo = cliente.totp_generate_code(semente) if semente else ""
    cliente.login(usuario, os.environ["IG_PASSWORD"], verification_code=codigo)


def _com_sessionid(cliente, _usuario: str) -> None:
    # cookie do navegador: pula o login com senha (que o Instagram às vezes recusa)
    cliente.login_by_sessionid(os.environ["IG_SESSIONID"])


JEITOS = {"senha": _com_senha, "sessionid": _com_sessionid}


def jeitos_de_login() -> list[str]:
    """Os jeitos escolhidos (BOT_IG_LOGIN), na ordem, que têm o dado necessário no .env."""
    return [jeito for jeito in lista("BOT_IG_LOGIN")
            if jeito in JEITOS and os.getenv(DADO_DO_LOGIN[jeito])]


def _novo_cliente():
    from instagrapi import Client  # pylint: disable=import-outside-toplevel

    # with_challenge_flow=False: sem isso um checkpoint trava o bot esperando input()
    # delay_range: espera antes de cada requisição, para parecer humano
    cliente = Client(delay_range=[0.5, 1.5], with_challenge_flow=False)
    if SESSAO.exists():
        cliente.load_settings(SESSAO)  # login repetido com senha é sinal de risco para o Instagram
    return cliente


def _entrar_com(jeito: str):
    usuario = os.environ["IG_USERNAME"].lstrip("@")
    cliente = _novo_cliente()
    try:
        JEITOS[jeito](cliente, usuario)
    finally:
        # salva mesmo se falhar: a próxima tentativa usa o mesmo "aparelho"
        SESSAO.parent.mkdir(parents=True, exist_ok=True)
        cliente.dump_settings(SESSAO)
    # trava: nunca ler/responder DMs por outra conta (ex.: cookie copiado da conta errada)
    if cliente.username.lower() != usuario.lower():
        raise RuntimeError(f"a sessão é da conta @{cliente.username}, não da @{usuario} (IG_USERNAME)")
    return cliente


def entrar() -> Entrada:
    """Tenta cada jeito de login, na ordem, até um funcionar. Lança erro se todos falharem."""
    falhas = []
    for jeito in jeitos_de_login():
        try:
            return Entrada(_entrar_com(jeito), jeito, falhas)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            falhas.append(f"{jeito}: {exc!r}{causa(exc)}")
    raise RuntimeError("nenhum jeito de login funcionou: " + ("; ".join(falhas) or "faltam dados no .env"))


def login():
    """O cliente logado (pelo primeiro jeito de login que funcionar)."""
    return entrar().cliente


def causa(exc) -> str:
    """O "needs_upgrade" costuma esconder a causa real (senha errada, 2FA, recuperação de conta,
    aprovação de aparelho). O instagrapi guarda a 1ª resposta do login na exceção: mostra só o
    motivo e os marcadores de etapa, sem o payload bruto."""
    resultado = getattr(exc, "caa_initial_outcome", None)
    if not isinstance(resultado, dict):
        return ""
    marcas = sorted({valor[:80] for valor in _textos(resultado)
                     if valor.startswith("CAA_") and ":" in valor})
    return f"\n   Motivo do 1º passo: {resultado.get('reason')!r}; etapas: {marcas}"


def _textos(valor):
    """Todos os textos dentro de dicts e listas aninhados."""
    if isinstance(valor, str):
        yield valor
    elif isinstance(valor, dict):
        for item in valor.values():
            yield from _textos(item)
    elif isinstance(valor, list):
        for item in valor:
            yield from _textos(item)


# ── a leitura da DM ──────────────────────────────────────────────────────────

def _enviar(cliente, thread_id: int, texto: str, enviados: set) -> int:
    partes = dividir(texto)
    for i, parte in enumerate(partes):
        if i:
            time.sleep(PAUSA_PARTES)
        enviados.add(cliente.direct_send(parte, thread_ids=[thread_id]).id)
    return len(partes)


def _ciclo(cliente, rota, thread_id: int, pular: set) -> None:
    """Uma leitura da DM: processa os comandos novos, do mais antigo ao mais novo."""
    for msg in sorted(cliente.direct_messages(thread_id, amount=20), key=lambda m: m.timestamp):
        texto = (msg.text or "").strip()
        if msg.id in pular or not texto.startswith("!"):
            continue
        atraso = (datetime.now(msg.timestamp.tzinfo) - msg.timestamp).total_seconds()
        inicio = time.monotonic()
        # a repetição é barrada no banco (como no Moodle); "ig_" evita colidir com ids do Moodle
        resposta = rota.post("/check_and_save", json={"id": f"ig_{msg.id}", "texto": texto}).json
        if not (resposta.get("status") == "new" and resposta.get("is_command") and resposta.get("resposta")):
            continue
        ia_pronta = time.monotonic()
        partes = _enviar(cliente, thread_id, resposta["resposta"], pular)
        print(f"[Instagram] {texto.split()[0]} recebido {atraso:.0f}s após o envio · "
              f"IA {ia_pronta - inicio:.0f}s · enviado em {partes} parte(s) "
              f"({time.monotonic() - ia_pronta:.0f}s)")


def _conectar():
    """Loga e acha a DM: (cliente, id da conversa, usuário da DM)."""
    cliente = login()
    alvo = os.environ["IG_THREAD"].lstrip("@")
    uid = cliente.user_id_from_username(alvo)
    thread_id = cliente._direct_thread_id_from_user_ids([uid], "text")  # pylint: disable=protected-access
    return cliente, thread_id, alvo


def _rodar(app) -> None:
    from instagrapi.exceptions import LoginRequired  # pylint: disable=import-outside-toplevel

    try:
        cliente, thread_id, alvo = _conectar()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"\n⚠️ Instagram desligado (o resto do bot segue funcionando): {exc!r}{causa(exc)}\n"
              "   Se for checkpoint/2FA, confirme o login no app do Instagram e reinicie.\n")
        return

    # o que já está na DM ao subir não dispara respostas (só o que chega com o bot rodando);
    # as respostas do próprio bot (enviadas como a conta) entram aqui e não são reprocessadas
    pular = {msg.id for msg in cliente.direct_messages(thread_id, amount=20)}
    print(f"📷 Instagram: escutando a DM com @{alvo}.")
    rota = app.test_client()
    while True:
        VIDA.touch()
        try:
            _ciclo(cliente, rota, thread_id, pular)
        except LoginRequired:
            cliente = login()  # a sessão caiu: entra de novo (já salva a sessão nova)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            print(f"[Instagram] erro: {exc!r}")
            time.sleep(60)  # PleaseWaitFewMinutes/429/rede: espera antes de tentar de novo
        time.sleep(INTERVALO + random.uniform(0, 2))


def faltando() -> list[str]:
    """O que falta no .env: usuário, DM e o dado de pelo menos um jeito de login escolhido."""
    falta = [nome for nome in ("IG_USERNAME", "IG_THREAD") if not os.getenv(nome)]
    if not jeitos_de_login():
        falta.append(" ou ".join(DADO_DO_LOGIN[jeito] for jeito in lista("BOT_IG_LOGIN") if jeito in JEITOS))
    return falta


def iniciar(app) -> "threading.Thread | None":
    """Sobe a leitura da DM numa thread, se o Instagram estiver configurado no .env."""
    VIDA.unlink(missing_ok=True)  # de uma execução anterior: o vigia só olha depois do login
    falta = faltando()
    if falta:
        print(f"\n⚠️ Instagram desligado: falta {', '.join(falta)} no .env.\n")
        return None
    thread = threading.Thread(target=_rodar, args=(app,), daemon=True, name="instagram")
    thread.start()
    return thread
