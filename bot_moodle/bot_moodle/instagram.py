"""Ponte DM do Instagram <-> rota /check_and_save: os mesmos comandos do Moodle.

Faz o papel da extensão: lê a DM de IG_THREAD, manda cada comando ("!...") para a rota
e responde na DM, quebrando em várias mensagens quando passa do limite.
"""

import os
import random
import threading
import time
from datetime import datetime
from pathlib import Path

# Meta documenta 1000 bytes UTF-8 por mensagem (acento = 2 bytes, emoji = 4); folga de 100
LIMITE_BYTES = 900
RESERVA_PREFIXO = 10      # espaço para "(12/34) "
INTERVALO = 4             # segundos entre leituras da DM (+ 0–2 s): mais rápido arrisca bloqueio
PAUSA_PARTES = 2.5        # segundos entre as partes de uma resposta longa (rajada parece spam)
SESSAO = Path("ig_session.json")
VIDA = Path(".instagram_vivo")  # tocado a cada leitura da DM; o vigia confere se não parou


def dividir(texto: str, limite: int = LIMITE_BYTES) -> list[str]:
    """Quebra em partes <= limite bytes, preferindo cortar em quebra de linha, depois em
    espaço. Mesma regra do dividirMensagem do content.js, mas contando bytes UTF-8."""
    max_bytes = limite - RESERVA_PREFIXO
    partes, resto = [], texto
    while len(resto.encode()) > max_bytes:
        # maior prefixo que cabe em max_bytes sem partir um caractere multibyte
        cabe = len(resto.encode()[:max_bytes].decode("utf-8", "ignore"))
        corte = resto.rfind("\n", 0, cabe)
        if corte < cabe // 2:
            corte = resto.rfind(" ", 0, cabe)
        if corte < cabe // 2:
            corte = cabe
        partes.append(resto[:corte])
        resto = resto[corte:]
        if resto[:1] in ("\n", " "):
            resto = resto[1:]
    partes.append(resto)
    if len(partes) == 1:
        return partes
    return [f"({i}/{len(partes)}) {p}" for i, p in enumerate(partes, 1)]


def login():
    """Loga reaproveitando a sessão salva e retorna o cliente."""
    from instagrapi import Client  # pylint: disable=import-outside-toplevel

    # with_challenge_flow=False: sem isso um checkpoint trava o bot esperando input()
    # delay_range: espera antes de cada requisição, para parecer humano
    cl = Client(delay_range=[0.5, 1.5], with_challenge_flow=False)
    if SESSAO.exists():
        cl.load_settings(SESSAO)  # reaproveita a sessão: login repetido com senha é sinal de risco
    usuario = os.environ["IG_USERNAME"].lstrip("@")
    try:
        if os.getenv("IG_SESSIONID"):
            # cookie do navegador: pula o login com senha (que o Instagram anda recusando)
            cl.login_by_sessionid(os.environ["IG_SESSIONID"])
        else:
            # com 2FA por app autenticador: o bot gera o código de 6 dígitos sozinho
            semente = os.getenv("IG_TOTP_SEED", "").replace(" ", "").upper()
            codigo = cl.totp_generate_code(semente) if semente else ""
            cl.login(usuario, os.environ["IG_PASSWORD"], verification_code=codigo)
    finally:
        # salva mesmo se falhar: a próxima tentativa usa o mesmo "aparelho"
        # (um aparelho novo a cada tentativa também é sinal de risco)
        cl.dump_settings(SESSAO)
    # trava: nunca ler/responder DMs por outra conta (ex.: cookie copiado da conta errada)
    if cl.username.lower() != usuario.lower():
        raise RuntimeError(f"a sessão é da conta @{cl.username}, não da @{usuario} (IG_USERNAME)")
    return cl


def causa(exc) -> str:
    """O "needs_upgrade" costuma esconder a causa real (senha errada, 2FA, recuperação
    de conta, aprovação de aparelho). O instagrapi guarda a 1ª resposta do login na
    exceção; mostra só o motivo e os marcadores de etapa, sem o payload bruto."""
    resultado = getattr(exc, "caa_initial_outcome", None)
    if not isinstance(resultado, dict):
        return ""
    marcas = set()

    def andar(valor):
        if isinstance(valor, dict):
            for v in valor.values():
                andar(v)
        elif isinstance(valor, list):
            for v in valor:
                andar(v)
        elif isinstance(valor, str) and valor.startswith("CAA_") and ":" in valor:
            marcas.add(valor[:80])

    andar(resultado)
    return f"\n   Motivo do 1º passo: {resultado.get('reason')!r}; etapas: {sorted(marcas)}"


def _enviar(cl, thread_id: int, texto: str, enviados: set) -> int:
    partes = dividir(texto)
    for i, parte in enumerate(partes):
        if i:
            time.sleep(PAUSA_PARTES)
        enviados.add(cl.direct_send(parte, thread_ids=[thread_id]).id)
    return len(partes)


def _ciclo(cl, cliente, thread_id: int, pular: set) -> None:
    """Uma leitura da DM: processa os comandos novos, do mais antigo ao mais novo."""
    for msg in sorted(cl.direct_messages(thread_id, amount=20), key=lambda m: m.timestamp):
        texto = (msg.text or "").strip()
        if msg.id in pular or not texto.startswith("!"):
            continue
        # dedup fica no banco (como no Moodle); "ig_" evita colisão com ids do Moodle
        atraso = (datetime.now(msg.timestamp.tzinfo) - msg.timestamp).total_seconds()
        t0 = time.monotonic()
        resp = cliente.post("/check_and_save", json={"id": f"ig_{msg.id}", "texto": texto}).json
        if resp.get("status") == "new" and resp.get("is_command") and resp.get("resposta"):
            t1 = time.monotonic()
            n = _enviar(cl, thread_id, resp["resposta"], pular)
            print(f"[Instagram] {texto.split()[0]} recebido {atraso:.0f}s após o envio · "
                  f"IA {t1 - t0:.0f}s · enviado em {n} parte(s) ({time.monotonic() - t1:.0f}s)")


def _rodar(app) -> None:
    from instagrapi.exceptions import LoginRequired  # pylint: disable=import-outside-toplevel

    try:
        cl = login()
        alvo = os.environ["IG_THREAD"].lstrip("@")
        uid = cl.user_id_from_username(alvo)
        thread_id = cl._direct_thread_id_from_user_ids([uid], "text")  # pylint: disable=protected-access
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"\n⚠️ Instagram desligado (o resto do bot segue funcionando): {exc!r}{causa(exc)}\n"
              "   Se for checkpoint/2FA, confirme o login no app do Instagram e reinicie.\n")
        return

    # o que já está na DM ao subir não dispara respostas (só o que chega com o bot rodando);
    # as respostas do próprio bot (enviadas como você) entram aqui e não são reprocessadas
    pular = {m.id for m in cl.direct_messages(thread_id, amount=20)}
    print(f"📷 Instagram: escutando a DM com @{alvo}.")

    cliente = app.test_client()
    while True:
        VIDA.touch()
        try:
            _ciclo(cl, cliente, thread_id, pular)
        except LoginRequired:
            cl = login()  # mesmo caminho do início (sessionid ou senha + 2FA); já salva a sessão
        except Exception as exc:  # pylint: disable=broad-exception-caught
            print(f"[Instagram] erro: {exc!r}")
            time.sleep(60)  # PleaseWaitFewMinutes/429/rede: espera antes de tentar de novo
        time.sleep(INTERVALO + random.uniform(0, 2))


def faltando() -> list[str]:
    """Variáveis do .env que faltam; IG_SESSIONID substitui IG_PASSWORD."""
    falta = [v for v in ("IG_USERNAME", "IG_THREAD") if not os.getenv(v)]
    if not (os.getenv("IG_PASSWORD") or os.getenv("IG_SESSIONID")):
        falta.append("IG_PASSWORD (ou IG_SESSIONID)")
    return falta


def iniciar(app) -> "threading.Thread | None":
    """Sobe a escuta da DM numa thread, se o Instagram estiver configurado no .env."""
    VIDA.unlink(missing_ok=True)  # de uma execução anterior: o vigia só olha depois do login
    falta = faltando()
    if falta:
        print(f"\n⚠️ Instagram desligado: falta {', '.join(falta)} no .env.\n")
        return None
    thread = threading.Thread(target=_rodar, args=(app,), daemon=True, name="instagram")
    thread.start()
    return thread
