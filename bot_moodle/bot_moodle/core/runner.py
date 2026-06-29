"""Compilação e execução interativa de código C com timer de silêncio."""

import re
import subprocess
import threading
import queue
import time

from bot_moodle.core.headers import corrigir_includes

# ─────────────────────────────────────────────────────────────────────────────
#  CONSTANTES
# ─────────────────────────────────────────────────────────────────────────────

SILENCE_TIMEOUT = 5.0  # segundos sem output → empacota resultado
_ARQUIVO_C = "/tmp/temp_codigo.c"
_BINARIO   = "/tmp/temp_executavel"

# ─────────────────────────────────────────────────────────────────────────────
#  ESTADO GLOBAL DA SESSÃO
# ─────────────────────────────────────────────────────────────────────────────

_estado: dict = {
    "proc":               None,
    "stdout_queue":       queue.Queue(),
    "stderr_queue":       queue.Queue(),
    "saida_lock":         threading.Lock(),
    "saida_buffer":       [],
    "resultado_pendente": None,
    "monitor_thread":     None,
    "ultimo_print":       0.0,   # 0.0 = nenhum output ainda; >0 = timestamp
    "ativo":              False,
    "encerrou":           False,
    # rastreamento do run atual
    "run_id":             None,
    "run_codigo":         None,
    "run_inputs":         [],
    "run_saida":          None,
}

# ─────────────────────────────────────────────────────────────────────────────
#  LEITURA ASSÍNCRONA
# ─────────────────────────────────────────────────────────────────────────────

def _ler_stream(stream, q: queue.Queue) -> None:
    """Lê um stream linha a linha e coloca na fila."""
    try:
        for linha in iter(stream.readline, ""):
            q.put(linha)
    except OSError:
        pass
    finally:
        try:
            stream.close()
        except OSError:
            pass


def _ler_saida_async(proc: subprocess.Popen) -> None:
    """Inicia threads de leitura para stdout e stderr."""
    threading.Thread(
        target=_ler_stream,
        args=(proc.stdout, _estado["stdout_queue"]),
        daemon=True,
    ).start()
    threading.Thread(
        target=_ler_stream,
        args=(proc.stderr, _estado["stderr_queue"]),
        daemon=True,
    ).start()


def _drenar_filas(timeout: float = 0.05) -> tuple[str, str]:
    """Drena stdout/stderr até o timeout; retorna (stdout, stderr)."""
    saida: list[str] = []
    erros: list[str] = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            saida.append(_estado["stdout_queue"].get_nowait())
        except queue.Empty:
            pass
        try:
            erros.append(_estado["stderr_queue"].get_nowait())
        except queue.Empty:
            pass
        time.sleep(0.01)
    return "".join(saida), "".join(erros)


# ─────────────────────────────────────────────────────────────────────────────
#  MONITOR DE SILÊNCIO
# ─────────────────────────────────────────────────────────────────────────────

def _empacotar_resultado(saida_completa: str, encerrou: bool, rc: int) -> str:
    """Monta a string de resultado final a ser entregue ao usuário."""
    if encerrou:
        msg = (
            f"✅ Saída:\n{saida_completa}"
            if saida_completa
            else "✅ Programa encerrado sem saída."
        )
        if rc != 0:
            msg += f"\n\n🔴 Código de saída: {rc}"
    else:
        msg = (
            f"✅ Saída (programa ainda em execução):\n{saida_completa}"
            if saida_completa
            else "⏳ Programa em execução mas sem saída nos últimos 5s."
        )
    return msg


def _monitor() -> None:
    """
    Acumula saída do processo e a empacota em resultado_pendente quando:
    - o processo encerra, ou
    - SILENCE_TIMEOUT segundos se passam após o primeiro output.
    O timer só começa depois do primeiro output (ultimo_print > 0.0).
    """
    while True:
        proc = _estado["proc"]
        if proc is None:
            break

        out, err = _drenar_filas(timeout=0.1)
        if out or err:
            with _estado["saida_lock"]:
                if out:
                    _estado["saida_buffer"].append(out)
                if err:
                    _estado["saida_buffer"].append(f"[stderr] {err}")
                _estado["ultimo_print"] = time.time()

        encerrou = proc.poll() is not None
        ultimo = _estado["ultimo_print"]
        timeout_atingido = (
            ultimo > 0.0 and (time.time() - ultimo) >= SILENCE_TIMEOUT
        )

        if not (encerrou or timeout_atingido):
            continue

        # Drenagem final
        time.sleep(0.3)
        out, err = _drenar_filas(timeout=0.5)
        with _estado["saida_lock"]:
            if out:
                _estado["saida_buffer"].append(out)
            if err:
                _estado["saida_buffer"].append(f"[stderr] {err}")
            saida_completa = "".join(_estado["saida_buffer"]).strip()
            _estado["saida_buffer"] = []

        rc = proc.returncode if encerrou else 0
        msg = _empacotar_resultado(saida_completa, encerrou, rc)

        with _estado["saida_lock"]:
            _estado["resultado_pendente"] = msg
            _estado["ultimo_print"] = 0.0

        if encerrou:
            _estado["ativo"]     = False
            _estado["encerrou"]  = True
            _estado["proc"]      = None
            _estado["run_saida"] = saida_completa
            break

    _estado["ativo"] = False


# ─────────────────────────────────────────────────────────────────────────────
#  LIMPEZA DE ESTADO
# ─────────────────────────────────────────────────────────────────────────────

def _limpar_estado() -> None:
    """Mata o processo ativo e reseta o estado de execução."""
    proc = _estado["proc"]
    if proc is not None:
        try:
            proc.kill()
        except OSError:
            pass
    _estado["proc"]               = None
    _estado["stdout_queue"]       = queue.Queue()
    _estado["stderr_queue"]       = queue.Queue()
    _estado["saida_buffer"]       = []
    _estado["resultado_pendente"] = None
    _estado["monitor_thread"]     = None
    _estado["ultimo_print"]       = 0.0
    _estado["ativo"]              = False
    _estado["encerrou"]           = False
    # run_id/run_codigo/run_inputs/run_saida permanecem até o próximo
    # compilar_e_executar, para permitir !chat+id após o encerramento.


# ─────────────────────────────────────────────────────────────────────────────
#  API PÚBLICA
# ─────────────────────────────────────────────────────────────────────────────

def verificar_resultado_pendente() -> "str | None":
    """Retorna e limpa o resultado pendente (chamado pelo server antes de cada request)."""
    with _estado["saida_lock"]:
        resultado = _estado["resultado_pendente"]
        _estado["resultado_pendente"] = None
    return resultado


def obter_dados_run() -> "dict | None":
    """
    Retorna os dados do run atual (id, codigo, inputs, saida) ou None.
    Usado pelo server para persistir e montar contexto de !chat+id.
    """
    if _estado["run_id"] is None:
        return None
    return {
        "id":     _estado["run_id"],
        "codigo": _estado["run_codigo"],
        "inputs": list(_estado["run_inputs"]),
        "saida":  _estado["run_saida"],
    }


def compilar_e_executar(codigo_c: str, run_id: "str | None" = None) -> str:
    """Compila e inicia execução. Retorna feedback imediato; saída vem via timer."""
    _limpar_estado()

    codigo_limpo = codigo_c.replace("```c", "").replace("```", "").strip()
    if not codigo_limpo:
        return "❌ Nenhum código foi enviado após !run."

    # [header.h] → <header.h>
    codigo_limpo = re.sub(r"#include\s*\[([^\]]+)\]", r"#include <\1>", codigo_limpo)
    codigo_limpo, avisos_include = corrigir_includes(codigo_limpo)

    # Força line-buffering (em pipe o C usa block-buffering por padrão)
    if "setvbuf" not in codigo_limpo:
        codigo_limpo = re.sub(
            r"(int\s+main\s*\([^)]*\)\s*\{)",
            r"\1\n    setvbuf(stdout, NULL, _IOLBF, 0);",
            codigo_limpo,
            count=1,
        )

    with open(_ARQUIVO_C, "w", encoding="utf-8") as f:
        f.write(codigo_limpo)

    compile_result = subprocess.run(
        ["gcc", _ARQUIVO_C, "-o", _BINARIO, "-Wall", "-lm"],
        capture_output=True,
        text=True,
        check=False,
    )
    if compile_result.returncode != 0:
        prefixo = "\n".join(avisos_include) + "\n\n" if avisos_include else ""
        return prefixo + f"❌ Erro de Compilação:\n{compile_result.stderr.strip()}"

    avisos_gcc = compile_result.stderr.strip()

    with subprocess.Popen(
        [_BINARIO],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=0,
    ) as proc:
        _estado["proc"]          = proc
        _estado["stdout_queue"]  = queue.Queue()
        _estado["stderr_queue"]  = queue.Queue()
        _estado["saida_buffer"]  = []
        _estado["ultimo_print"]  = 0.0
        _estado["ativo"]         = True
        _estado["encerrou"]      = False
        _estado["run_id"]        = run_id
        _estado["run_codigo"]    = codigo_limpo
        _estado["run_inputs"]    = []
        _estado["run_saida"]     = None

        _ler_saida_async(proc)
        t = threading.Thread(target=_monitor, daemon=True)
        _estado["monitor_thread"] = t
        t.start()

        prefixo = ""
        if avisos_include:
            prefixo += "\n".join(avisos_include) + "\n\n"
        if avisos_gcc:
            prefixo += f"⚠️ Avisos de Compilação:\n{avisos_gcc}\n\n"

        return (
            prefixo
            + "⏳ Programa em execução e aguardando entrada.\n"
            "Use !r <valor> para enviar input. "
            "A saída será entregue após 5s de silêncio ou quando você usar !kill."
        )


def enviar_input(valor: str) -> str:
    """Envia um valor ao programa em execução (comando !r)."""
    if _estado.get("encerrou"):
        return (
            "⚠️ O programa já encerrou. "
            "Use !kill para ver a saída ou envie !run para um novo código."
        )

    proc = _estado.get("proc")
    if proc is None or proc.poll() is not None:
        _limpar_estado()
        return "❌ Nenhum programa está aguardando input no momento."

    try:
        proc.stdin.write(valor.strip() + "\n")
        proc.stdin.flush()
        _estado["run_inputs"].append(valor.strip())
    except BrokenPipeError:
        return "⚠️ O programa encerrou ao receber o input. Aguarde a saída ou use !kill."

    return "⏳ Input enviado. Aguardando próxima entrada ou saída do programa."


def matar_processo() -> str:
    """Mata o processo ativo e entrega todo o output acumulado imediatamente."""
    proc = _estado.get("proc")

    if _estado.get("encerrou") or (
        proc is None and _estado.get("resultado_pendente")
    ):
        pendente = verificar_resultado_pendente()
        _limpar_estado()
        if pendente:
            return f"✅ Programa já havia encerrado. Saída:\n\n{pendente}"
        return "⚠️ Nenhum programa estava em execução no momento."

    if proc is None or proc.poll() is not None:
        pendente = verificar_resultado_pendente()
        _limpar_estado()
        if pendente:
            return f"🔴 Processo já tinha encerrado. Saída pendente:\n\n{pendente}"
        return "⚠️ Nenhum programa estava em execução no momento."

    try:
        proc.kill()
        proc.wait(timeout=2)
    except OSError:
        pass

    time.sleep(0.3)
    out, err = _drenar_filas(timeout=0.5)

    with _estado["saida_lock"]:
        if out:
            _estado["saida_buffer"].append(out)
        if err:
            _estado["saida_buffer"].append(f"[stderr] {err}")
        saida_completa = "".join(_estado["saida_buffer"]).strip()
        pendente = _estado["resultado_pendente"]

    _limpar_estado()

    partes = []
    if pendente:
        partes.append(pendente)
    if saida_completa:
        partes.append(f"✅ Saída final:\n{saida_completa}")

    if partes:
        return "🔴 Programa encerrado pelo !kill.\n\n" + "\n\n".join(partes)
    return "🔴 Programa encerrado pelo !kill. Sem saída adicional."
