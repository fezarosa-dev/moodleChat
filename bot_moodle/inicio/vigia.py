"""O vigia: sobe o bot num processo filho e o reinicia, com as mesmas preferências, se ele cair
ou travar. Ctrl+C para os dois.

"Travar" é: o servidor da extensão parar de responder em /health (depois de ter respondido uma
vez: com a reserva, ele pode nem subir), ou o Moodle/Instagram parar de tocar o seu arquivo de vida
(em dados/) por PARADO_S segundos.
"""

import os
import subprocess
import sys
import time
import urllib.request

from bot_moodle.plataformas import instagram, moodle

PING_S = 30                  # de quanto em quanto tempo confere o bot
CARENCIA_S = 60              # tempo para subir (login do Instagram etc.) antes de conferir
FALHAS_MAX = 4               # 4 pings sem resposta (2 min) = servidor travado
PARADO_S = 15 * 60           # sem ler mensagens: maior que uma resposta passando por todas as IAs
LIMITE, JANELA_S = 5, 10 * 60  # freio: 5 reinícios em 10 min e desiste
NAO_REINICIAR = 3            # código de saída do bot quando reiniciar não adianta (ex.: login)
# Ctrl+C chega também no filho: estes códigos são ele parando, não caindo.
# 0: o Flask engole o Ctrl+C e sai normal (no Windows o vigia só vê isso)
CODIGOS_CTRL_C = {0, -2, 130, 0xC000013A}
VIDAS = {"Instagram": instagram.VIDA, "Moodle (API)": moodle.VIDA}


def _parar(filho: subprocess.Popen) -> None:
    filho.terminate()
    try:
        filho.wait(10)
    except subprocess.TimeoutExpired:
        filho.kill()
        filho.wait()


def _esperar_saida(filho: subprocess.Popen) -> "int | None":
    """O código de saída do filho, ou None se ele continua rodando depois de PING_S segundos."""
    try:
        return filho.wait(timeout=PING_S)
    except subprocess.TimeoutExpired:
        return None


def _motivo_da_saida(codigo: int) -> str:
    """Por que o filho saiu. Ctrl+C e erros que reiniciar não resolve param o vigia também."""
    if codigo in CODIGOS_CTRL_C:
        raise KeyboardInterrupt
    if codigo == NAO_REINICIAR:
        raise SystemExit("❌ O bot parou e reiniciar não resolve (veja o erro acima).")
    return f"o bot caiu (código {codigo})"


def _servidor_responde(porta: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/health", timeout=10):
            return True
    except OSError:
        return False


def _plataforma_parada() -> "str | None":
    """A plataforma que parou de ler mensagens (o arquivo de vida só existe depois que ela começa)."""
    paradas = [nome for nome, vida in VIDAS.items()
               if vida.exists() and time.time() - vida.stat().st_mtime > PARADO_S]
    return paradas[0] if paradas else None


def vigiar(filho: subprocess.Popen, servidor: bool, porta: int) -> str:
    """Espera o filho cair ou travar e devolve o motivo (com o filho já parado)."""
    inicio, falhas, servidor_visto = time.monotonic(), 0, False
    while True:
        codigo = _esperar_saida(filho)
        if codigo is not None:
            return _motivo_da_saida(codigo)
        if time.monotonic() - inicio < CARENCIA_S:
            continue
        responde = servidor and _servidor_responde(porta)
        servidor_visto = servidor_visto or responde
        falhas = falhas + 1 if servidor_visto and not responde else 0
        if falhas >= FALHAS_MAX:
            _parar(filho)
            return f"o servidor não responde há {FALHAS_MAX * PING_S // 60} min"
        parada = _plataforma_parada()
        if parada:
            _parar(filho)
            return f"o {parada} parou de ler as mensagens há {PARADO_S // 60} min"


def _apagar_vidas() -> None:
    """Arquivos de vida de uma execução anterior (ou de uma plataforma agora desligada) fariam o
    vigia achar que o bot travou."""
    for vida in VIDAS.values():
        vida.unlink(missing_ok=True)


def rodar(servidor: bool) -> None:
    """Sobe o bot e o mantém de pé até o Ctrl+C."""
    porta = int(os.getenv("PORT", "5000"))
    ambiente = {**os.environ, "BOT_VIGIADO": "1"}
    reinicios: list[float] = []
    print("🛡️  Vigia ligado: reinicia o bot se ele cair ou travar (Ctrl+C para tudo).")
    filho = None
    try:
        while True:
            _apagar_vidas()
            filho = subprocess.Popen(  # pylint: disable=consider-using-with
                [sys.executable, "-m", "bot_moodle.app"], env=ambiente)
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
