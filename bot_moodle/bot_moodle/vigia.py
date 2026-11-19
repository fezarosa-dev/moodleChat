"""Vigia: sobe o bot num processo filho e o reinicia, com as mesmas preferências,
se ele cair ou travar. Ctrl+C para os dois.
"""

import os
import subprocess
import sys
import time
import urllib.request

from bot_moodle import instagram, moodle_api

PING_S = 30                  # de quanto em quanto tempo confere o bot
CARENCIA_S = 60              # tempo para subir (login do Instagram etc.) antes de conferir
FALHAS_MAX = 4               # 4 pings sem resposta (2 min) = servidor travado
PARADO_S = 15 * 60           # sem ler mensagens: maior que uma resposta passando por todas as IAs
VIDAS = {"Instagram": instagram.VIDA, "Moodle (API)": moodle_api.VIDA}
LIMITE, JANELA_S = 5, 10 * 60  # freio: 5 reinícios em 10 min e desiste
NAO_REINICIAR = 3            # código de saída do bot quando reiniciar não adianta (ex.: login)
# Ctrl+C chega também no filho: estes códigos são ele parando, não caindo.
# 0: o Flask engole o Ctrl+C e sai normal (no Windows o vigia só vê isso)
CODIGOS_CTRL_C = {0, -2, 130, 0xC000013A}


def _parar(filho: subprocess.Popen) -> None:
    filho.terminate()
    try:
        filho.wait(10)
    except subprocess.TimeoutExpired:
        filho.kill()
        filho.wait()


def vigiar(filho: subprocess.Popen, servidor: bool, porta: int) -> str:
    """Espera o filho cair ou travar e devolve o motivo (o filho já parado)."""
    inicio, falhas = time.monotonic(), 0
    while True:
        try:
            codigo = filho.wait(timeout=PING_S)
        except subprocess.TimeoutExpired:
            codigo = None
        if codigo is not None:
            if codigo in CODIGOS_CTRL_C:
                raise KeyboardInterrupt
            if codigo == NAO_REINICIAR:
                raise SystemExit("❌ O bot parou e reiniciar não resolve (veja o erro acima).")
            return f"o bot caiu (código {codigo})"
        if time.monotonic() - inicio < CARENCIA_S:
            continue
        if servidor:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{porta}/health", timeout=10):
                    falhas = 0
            except OSError:
                falhas += 1
            if falhas >= FALHAS_MAX:
                _parar(filho)
                return f"o servidor não responde há {FALHAS_MAX * PING_S // 60} min"
        # cada arquivo só existe depois que a plataforma começou a ler as mensagens
        for nome, vida in VIDAS.items():
            if vida.exists() and time.time() - vida.stat().st_mtime > PARADO_S:
                _parar(filho)
                return f"o {nome} parou de ler as mensagens há {PARADO_S // 60} min"


def rodar(servidor: bool) -> None:
    """Sobe o bot e o mantém de pé."""
    porta = int(os.getenv("PORT", "5000"))
    env = {**os.environ, "BOT_VIGIADO": "1"}
    reinicios: list[float] = []
    print("🛡️  Vigia ligado: reinicia o bot se ele cair ou travar (Ctrl+C para tudo).")
    filho = None
    try:
        while True:
            # de uma execução anterior (ou de uma plataforma desligada agora): parecia travada
            for vida in VIDAS.values():
                vida.unlink(missing_ok=True)
            filho = subprocess.Popen(  # pylint: disable=consider-using-with
                [sys.executable, "-m", "bot_moodle.app"], env=env)
            motivo = vigiar(filho, servidor, porta)
            agora = time.monotonic()
            reinicios = [t for t in reinicios if agora - t < JANELA_S] + [agora]
            if len(reinicios) > LIMITE:
                sys.exit(f"❌ {motivo}, e já reiniciou {LIMITE} vezes em {JANELA_S // 60} min: "
                         "desistindo para não ficar em loop (veja os erros acima).")
            print(f"\n🔁 {motivo}: reiniciando ({len(reinicios)}/{LIMITE} em {JANELA_S // 60} min)...\n")
    except KeyboardInterrupt:
        print("\n👋 Parando o bot...")
        if filho and filho.poll() is None:
            _parar(filho)
