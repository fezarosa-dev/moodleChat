import subprocess
import os
import re
import threading
import queue
import time

# ─────────────────────────────────────────────────────────────────────────────
#  ESTADO GLOBAL DA SESSÃO
# ─────────────────────────────────────────────────────────────────────────────

_estado = {
    "proc":           None,         # subprocess.Popen ativo
    "stdout_queue":   queue.Queue(),
    "stderr_queue":   queue.Queue(),
    "saida_lock":     threading.Lock(),
    "saida_buffer":   [],           # linhas acumuladas desde o último flush
    "resultado_pendente": None,     # string pronta para entregar ao usuário
    "monitor_thread": None,         # thread do timer de silêncio
    "ultimo_print":   0.0,          # 0.0 = nunca printou nada ainda; >0 = timestamp do último print
    "ativo":          False,        # True enquanto o processo vive
    "encerrou":       False,        # True quando processo encerrou naturalmente (resultado já salvo)
}

SILENCE_TIMEOUT = 5.0   # segundos sem output → empacota resultado


# ─────────────────────────────────────────────────────────────────────────────
#  LEITURA ASSÍNCRONA  stdout / stderr
# ─────────────────────────────────────────────────────────────────────────────

def _ler_saida_async(proc):
    """Inicia threads que jogam linhas nas filas."""
    def _stream(stream, q):
        try:
            for linha in iter(stream.readline, ''):
                q.put(linha)
        except Exception:
            pass
        finally:
            try:
                stream.close()
            except Exception:
                pass

    threading.Thread(target=_stream, args=(proc.stdout, _estado["stdout_queue"]), daemon=True).start()
    threading.Thread(target=_stream, args=(proc.stderr, _estado["stderr_queue"]), daemon=True).start()


def _drenar_filas(timeout=0.05) -> tuple[str, str]:
    """Drena tudo que estiver nas filas agora; retorna (stdout, stderr)."""
    saida, erros = [], []
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
#  THREAD DE MONITORAMENTO (timer de silêncio)
# ─────────────────────────────────────────────────────────────────────────────

def _monitor():
    """
    Fica acumulando saída no buffer global.

    Regras do timer:
    - Enquanto ultimo_print == 0.0, o programa nunca printou nada → timer inativo,
      aguarda indefinidamente (só encerra se o processo morrer).
    - Assim que o primeiro output chega, ultimo_print recebe o timestamp e o
      countdown de SILENCE_TIMEOUT começa.
    - A cada novo output, o timer reseta.
    - Quando o processo encerra OU o silêncio >= SILENCE_TIMEOUT após o primeiro
      output, empacota tudo em resultado_pendente.
    """
    while True:
        proc = _estado["proc"]
        if proc is None:
            break

        # Drena o que chegou
        out, err = _drenar_filas(timeout=0.1)

        if out or err:
            with _estado["saida_lock"]:
                if out:
                    _estado["saida_buffer"].append(out)
                if err:
                    _estado["saida_buffer"].append(f"[stderr] {err}")
                _estado["ultimo_print"] = time.time()   # ativa/reseta o timer

        # Verifica se processo encerrou
        encerrou = proc.poll() is not None

        # Silêncio suficiente? Só conta se já houve ao menos um output.
        ultimo = _estado["ultimo_print"]
        timeout_atingido = (ultimo > 0.0) and (time.time() - ultimo >= SILENCE_TIMEOUT)

        if encerrou or timeout_atingido:
            # Drenagem final generosa
            time.sleep(0.3)
            out, err = _drenar_filas(timeout=0.5)
            with _estado["saida_lock"]:
                if out:
                    _estado["saida_buffer"].append(out)
                if err:
                    _estado["saida_buffer"].append(f"[stderr] {err}")

                saida_completa = "".join(_estado["saida_buffer"]).strip()
                _estado["saida_buffer"] = []

            # Monta mensagem de resultado
            if encerrou:
                rc = proc.returncode
                if saida_completa:
                    msg = f"✅ Saída:\n{saida_completa}"
                else:
                    msg = "✅ Programa encerrado sem saída."
                if rc != 0:
                    msg += f"\n\n🔴 Código de saída: {rc}"
            else:
                # Timeout de silêncio — programa ainda rodando
                if saida_completa:
                    msg = f"✅ Saída (programa ainda em execução):\n{saida_completa}"
                else:
                    msg = "⏳ Programa em execução mas sem saída nos últimos 5s."

            with _estado["saida_lock"]:
                _estado["resultado_pendente"] = msg
                _estado["ultimo_print"] = 0.0   # reseta para próximo ciclo

            if encerrou:
                # Marca como encerrado mas NÃO limpa o estado agora —
                # resultado_pendente precisa ficar acessível para a próxima request.
                _estado["ativo"]    = False
                _estado["encerrou"] = True
                _estado["proc"]     = None   # sinaliza que não tem mais processo vivo
                break

            # Processo ainda rodando → entrega o output parcial e continua monitorando

    _estado["ativo"] = False


# ─────────────────────────────────────────────────────────────────────────────
#  VERIFICAÇÃO DE RESULTADO PENDENTE  (chamada pelo server.py antes de qualquer cmd)
# ─────────────────────────────────────────────────────────────────────────────

def verificar_resultado_pendente() -> str | None:
    """
    Retorna e limpa o resultado pendente, se houver.
    O server.py deve chamar isso no início de CADA request.
    """
    with _estado["saida_lock"]:
        resultado = _estado["resultado_pendente"]
        _estado["resultado_pendente"] = None
    return resultado


# ─────────────────────────────────────────────────────────────────────────────
#  INFERÊNCIA DE HEADERS C
# ─────────────────────────────────────────────────────────────────────────────

_HEADERS_INFERIDOS = [
    (r"\bprintf\b|\bscanf\b|\bputchar\b|\bgetchar\b|\bputs\b|\bgets\b"
     r"|\bfopen\b|\bfclose\b|\bfprintf\b|\bfscanf\b|\bfflush\b|\bperror\b"
     r"|\bfread\b|\bfwrite\b|\bfseek\b|\bftell\b|\brewind\b|\bfeof\b"
     r"|\bsscanf\b|\bsprintf\b|\bsnprintf\b|\bvprintf\b|\bgetline\b|\bfgets\b|\bfputs\b",
     "stdio.h"),
    (r"\bmalloc\b|\bcalloc\b|\brealloc\b|\bfree\b|\bexit\b|\babort\b"
     r"|\batoi\b|\batof\b|\batol\b|\batoll\b|\bstrtol\b|\bstrtod\b|\bstrtof\b"
     r"|\brand\b|\bsrand\b|\babs\b|\bdiv\b|\bqsort\b|\bbsearch\b"
     r"|\bgetenv\b|\bsystem\b|\bNULL\b|\bsize_t\b",
     "stdlib.h"),
    (r"\bstrlen\b|\bstrcpy\b|\bstrncpy\b|\bstrcat\b|\bstrncat\b"
     r"|\bstrcmp\b|\bstrncmp\b|\bstrchr\b|\bstrrchr\b|\bstrstr\b"
     r"|\bstrtok\b|\bstrdup\b|\bmemset\b|\bmemcpy\b|\bmemmove\b|\bmemcmp\b",
     "string.h"),
    (r"\bsqrt\b|\bpow\b|\bfabs\b|\bceil\b|\bfloor\b|\bround\b|\btrunc\b"
     r"|\bsin\b|\bcos\b|\btan\b|\basin\b|\bacos\b|\batan\b|\batan2\b"
     r"|\blog\b|\blog2\b|\blog10\b|\bexp\b|\bexp2\b|\bhypot\b|\bfmod\b"
     r"|\bM_PI\b|\bINFINITY\b|\bNAN\b|\bisnan\b|\bisinf\b",
     "math.h"),
    (r"\bisalpha\b|\bisdigit\b|\bisspace\b|\bisupper\b|\bislower\b"
     r"|\btoupper\b|\btolower\b|\bisalnum\b|\bispunct\b|\bisprint\b"
     r"|\bisblank\b|\biscntrl\b|\bisxdigit\b",
     "ctype.h"),
    (r"\btime\b|\bclock\b|\bdifftime\b|\bmktime\b|\blocaltime\b"
     r"|\bgmtime\b|\bstrftime\b|\btime_t\b|\bstruct\s+tm\b|\bclock_t\b",
     "time.h"),
    (r"\bINT_MAX\b|\bINT_MIN\b|\bUINT_MAX\b|\bLONG_MAX\b|\bLONG_MIN\b"
     r"|\bSHRT_MAX\b|\bCHAR_MAX\b|\bUCHAR_MAX\b|\bULONG_MAX\b",
     "limits.h"),
    (r"\bFLT_MAX\b|\bFLT_MIN\b|\bDBL_MAX\b|\bDBL_MIN\b|\bFLT_EPSILON\b|\bDBL_EPSILON\b",
     "float.h"),
    (r"\bint8_t\b|\bint16_t\b|\bint32_t\b|\bint64_t\b"
     r"|\buint8_t\b|\buint16_t\b|\buint32_t\b|\buint64_t\b"
     r"|\bintptr_t\b|\buintptr_t\b|\bPRId32\b|\bPRIu64\b",
     "stdint.h"),
    (r"\bbool\b|\btrue\b|\bfalse\b",  "stdbool.h"),
    (r"\bassert\b",                    "assert.h"),
    (r"\bsignal\b|\braise\b|\bSIGINT\b|\bSIGSEGV\b|\bSIGTERM\b|\bSIG_DFL\b", "signal.h"),
    (r"\bsetjmp\b|\blongjmp\b|\bjmp_buf\b",                                     "setjmp.h"),
    (r"\bva_list\b|\bva_start\b|\bva_arg\b|\bva_end\b|\bva_copy\b",             "stdarg.h"),
    (r"\berrno\b|\bERANGE\b|\bEDOM\b|\bENOMEM\b|\bEINVAL\b",                   "errno.h"),
    (r"\bsetlocale\b|\blocaleconv\b|\bLC_ALL\b|\bLC_NUMERIC\b|\bLC_TIME\b",     "locale.h"),
]


def _corrigir_includes(codigo: str) -> tuple[str, list[str]]:
    linhas = codigo.split('\n')
    avisos = []
    presentes = set()
    indices_vazios = []

    for i, linha in enumerate(linhas):
        s = linha.strip()
        if s.startswith('#include') and ('<' in s or '"' in s):
            m = re.search(r'[<"]([^>"]+)[>"]', s)
            if m:
                presentes.add(m.group(1))
        elif re.match(r'^#include\s*$', s):
            indices_vazios.append(i)

    if not indices_vazios:
        return codigo, avisos

    necessarios = [h for p, h in _HEADERS_INFERIDOS if h not in presentes and re.search(p, codigo)]
    if not necessarios:
        necessarios = ["stdio.h"]

    avisos.append(
        f"⚠️ Aviso: {len(indices_vazios)} diretiva(s) '#include' incompleta(s) detectada(s) "
        f"(provavelmente removidas pelo chat). "
        f"Inferido(s) automaticamente: {', '.join(necessarios)}."
    )

    for idx, linha_idx in enumerate(indices_vazios):
        if idx < len(necessarios):
            if idx == len(indices_vazios) - 1 and len(necessarios) > len(indices_vazios):
                extras = necessarios[idx:]
                linhas[linha_idx] = "\n".join(f"#include <{h}>" for h in extras)
            else:
                linhas[linha_idx] = f"#include <{necessarios[idx]}>"
        else:
            linhas[linha_idx] = ""

    return '\n'.join(linhas), avisos


# ─────────────────────────────────────────────────────────────────────────────
#  LIMPEZA DE ESTADO
# ─────────────────────────────────────────────────────────────────────────────

def _limpar_estado():
    proc = _estado["proc"]
    if proc is not None:
        try:
            proc.kill()
        except Exception:
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


# ─────────────────────────────────────────────────────────────────────────────
#  API PÚBLICA
# ─────────────────────────────────────────────────────────────────────────────

def compilar_e_executar(codigo_c: str) -> str:
    """Compila e inicia a execução. Retorna feedback imediato; saída vem via timer."""
    _limpar_estado()

    arquivo_c = "/tmp/temp_codigo.c"
    binario   = "/tmp/temp_executavel"

    codigo_limpo = codigo_c.replace("```c", "").replace("```", "").strip()
    if not codigo_limpo:
        return "❌ Nenhum código foi enviado após !run."

    # Converte #include [header.h] → #include <header.h> (enviado pelo navegador para evitar conflito com HTML)
    codigo_limpo = re.sub(r'#include\s*\[([^\]]+)\]', r'#include <\1>', codigo_limpo)

    codigo_limpo, avisos_include = _corrigir_includes(codigo_limpo)

    # Força line-buffering para não perder prompts em pipe
    if 'setvbuf' not in codigo_limpo:
        codigo_limpo = re.sub(
            r'(int\s+main\s*\([^)]*\)\s*\{)',
            r'\1\n    setvbuf(stdout, NULL, _IOLBF, 0);',
            codigo_limpo,
            count=1
        )

    with open(arquivo_c, "w") as f:
        f.write(codigo_limpo)

    compile_result = subprocess.run(
        ["gcc", arquivo_c, "-o", binario, "-Wall", "-lm"],
        capture_output=True, text=True
    )
    if compile_result.returncode != 0:
        msg = ""
        if avisos_include:
            msg += "\n".join(avisos_include) + "\n\n"
        msg += f"❌ Erro de Compilação:\n{compile_result.stderr.strip()}"
        return msg

    avisos_gcc = compile_result.stderr.strip()

    try:
        proc = subprocess.Popen(
            [binario],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=0,
        )
    except Exception as e:
        return f"❌ Erro ao iniciar o executável: {e}"

    # Registra no estado global
    _estado["proc"]          = proc
    _estado["stdout_queue"]  = queue.Queue()
    _estado["stderr_queue"]  = queue.Queue()
    _estado["saida_buffer"]  = []
    _estado["ultimo_print"]  = 0.0    # timer INATIVO até o primeiro output chegar
    _estado["ativo"]         = True
    _estado["encerrou"]      = False

    _ler_saida_async(proc)

    # Inicia o monitor de silêncio
    t = threading.Thread(target=_monitor, daemon=True)
    _estado["monitor_thread"] = t
    t.start()

    # Monta prefixo de avisos
    prefixo = ""
    if avisos_include:
        prefixo += "\n".join(avisos_include) + "\n\n"
    if avisos_gcc:
        prefixo += f"⚠️ Avisos de Compilação:\n{avisos_gcc}\n\n"

    return (
        prefixo +
        "⏳ Programa em execução e aguardando entrada.\n"
        "Use !r <valor> para enviar input. "
        "A saída será entregue após 5s de silêncio ou quando você usar !kill."
    )


def enviar_input(valor: str) -> str:
    """Envia um valor ao programa em execução (comando !r)."""
    proc = _estado.get("proc")

    # Processo já encerrou (naturalmente) — resultado está em resultado_pendente
    if _estado.get("encerrou"):
        return "⚠️ O programa já encerrou. Use !kill para ver a saída ou envie !run para um novo código."

    if proc is None or proc.poll() is not None:
        # Processo morreu inesperadamente
        _limpar_estado()
        return "❌ Nenhum programa está aguardando input no momento."

    try:
        proc.stdin.write(valor.strip() + "\n")
        proc.stdin.flush()
    except BrokenPipeError:
        # Processo encerrou enquanto enviávamos — o monitor vai capturar a saída
        return "⚠️ O programa encerrou ao receber o input. Aguarde a saída ou use !kill."

    return "⏳ Input enviado. Aguardando próxima entrada ou saída do programa."


def matar_processo() -> str:
    """Mata o processo ativo e entrega todo o output acumulado imediatamente."""
    proc = _estado.get("proc")

    # Processo já encerrou naturalmente (encerrou=True) — só entrega o pendente
    if _estado.get("encerrou") or (proc is None and _estado.get("resultado_pendente")):
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

    # Para o processo forçadamente
    try:
        proc.kill()
        proc.wait(timeout=2)
    except Exception:
        pass

    # Coleta tudo que sobrou nos buffers
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
