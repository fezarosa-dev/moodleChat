"""!run, !r e !kill: compila código C, roda com entrada interativa e entrega a saída.

Cada !run vira uma Execucao. Uma thread (o monitor) junta a saída do programa e a entrega quando
ele termina ou fica SILENCE_TIMEOUT segundos sem escrever nada; a resposta espera em `pendente`
até a próxima mensagem do chat. Cada monitor só mexe na própria execução: um !run novo não é
confundido com o anterior.
"""

import os
import queue
import re
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field

from bot_moodle.execucao.headers import corrigir_includes

SILENCE_TIMEOUT = 5.0  # segundos sem output -> entrega o que juntou
# pasta temporária do sistema (/tmp no Linux, %TEMP% no Windows, onde o gcc gera .exe)
_ARQUIVO_C = os.path.join(tempfile.gettempdir(), "temp_codigo.c")
_BINARIO = os.path.join(tempfile.gettempdir(), "temp_executavel" + (".exe" if os.name == "nt" else ""))
# stdout sem buffer: em pipe o C guarda a saída em blocos e ela só apareceria no fim (ou se
# perderia no !kill). _IONBF e não _IOLBF: no Windows o _IOLBF vira buffer cheio
_SETVBUF = r"\1\n    setvbuf(stdout, NULL, _IONBF, 0);"
_INICIO_DO_MAIN = r"(int\s+main\s*\([^)]*\)\s*\{)"

NENHUM_PROGRAMA = "⚠️ Nenhum programa estava em execução no momento."


@dataclass
class Execucao:  # pylint: disable=too-many-instance-attributes
    """Um programa rodando (ou que rodou): processo, saída acumulada e dados para o contexto."""

    processo: "subprocess.Popen | None" = None
    run_id: "str | None" = None
    codigo: "str | None" = None
    entradas: list = field(default_factory=list)
    saida_final: "str | None" = None
    pendente: "str | None" = None
    encerrou: bool = False
    ultimo_print: float = 0.0  # 0.0 = ainda não escreveu nada
    _stdout: queue.Queue = field(default_factory=queue.Queue)
    _stderr: queue.Queue = field(default_factory=queue.Queue)
    _acumulado: list = field(default_factory=list)
    _trava: threading.Lock = field(default_factory=threading.Lock)

    def iniciar(self) -> None:
        """Abre o programa e as threads que leem a saída e a entregam."""
        # sem `with`: ele fecharia os pipes ao retornar e o programa receberia EOF antes do !r
        self.processo = subprocess.Popen(  # pylint: disable=consider-using-with
            [_BINARIO], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", bufsize=0)  # cp1252 no Windows quebraria acentos
        for stream, fila in ((self.processo.stdout, self._stdout), (self.processo.stderr, self._stderr)):
            threading.Thread(target=_ler_stream, args=(stream, fila), daemon=True).start()
        threading.Thread(target=self._monitorar, daemon=True).start()

    def rodando(self) -> bool:
        """O processo existe e ainda não terminou."""
        return self.processo is not None and self.processo.poll() is None

    def parar(self) -> None:
        """Mata o processo e descarta o que não foi entregue (mantém os dados do run)."""
        processo, self.processo = self.processo, None
        if processo is not None:
            _matar(processo)
        with self._trava:
            self._acumulado, self.pendente, self.encerrou = [], None, False

    def tirar_pendente(self) -> "str | None":
        """A saída pronta para o chat (e a apaga); None se não há nada."""
        with self._trava:
            pendente, self.pendente = self.pendente, None
        return pendente

    def guardar(self, saida: str, erros: str) -> None:
        """Junta um pedaço da saída (stderr marcado) ao acumulado."""
        with self._trava:
            self._acumulado += [saida] if saida else []
            self._acumulado += [f"[stderr] {erros}"] if erros else []
            self.ultimo_print = time.time() if saida or erros else self.ultimo_print

    def tirar_acumulado(self) -> str:
        """A saída juntada desde a última entrega (e a apaga)."""
        with self._trava:
            texto, self._acumulado = "".join(self._acumulado).strip(), []
        return texto

    def drenar(self, timeout: float) -> tuple[str, str]:
        """Lê stdout e stderr por `timeout` segundos."""
        saida, erros = [], []
        limite = time.time() + timeout
        while time.time() < limite:
            saida += _tirar_sem_esperar(self._stdout)
            erros += _tirar_sem_esperar(self._stderr)
            time.sleep(0.01)
        return "".join(saida), "".join(erros)

    def _hora_de_entregar(self, processo) -> bool:
        if processo.poll() is not None:
            return True
        return self.ultimo_print > 0.0 and time.time() - self.ultimo_print >= SILENCE_TIMEOUT

    def _monitorar(self) -> None:
        """Entrega a saída quando o programa termina ou fica em silêncio (depois de escrever algo)."""
        processo = self.processo
        while processo is not None and self.processo is processo:
            self.guardar(*self.drenar(timeout=0.1))
            if not self._hora_de_entregar(processo):
                continue
            time.sleep(0.3)  # drenagem final
            self.guardar(*self.drenar(timeout=0.5))
            if self._entregar(processo):
                return

    def _entregar(self, processo) -> bool:
        """Deixa a saída pendente; True se o programa terminou (o monitor para)."""
        encerrou = processo.poll() is not None
        saida = self.tirar_acumulado()
        with self._trava:
            if self.processo is not processo:  # foi parada no meio: não entrega nada
                return True
            self.pendente = _empacotar(saida, encerrou, processo.returncode if encerrou else 0)
            self.ultimo_print = 0.0
            if encerrou:
                self.encerrou, self.processo, self.saida_final = True, None, saida
        return encerrou


def _ler_stream(stream, fila: queue.Queue) -> None:
    try:
        for linha in iter(stream.readline, ""):
            fila.put(linha)
    except OSError:
        pass
    finally:
        try:
            stream.close()
        except OSError:
            pass


def _tirar_sem_esperar(fila: queue.Queue) -> list[str]:
    try:
        return [fila.get_nowait()]
    except queue.Empty:
        return []


def _matar(processo: subprocess.Popen) -> None:
    try:
        processo.kill()
        processo.wait(timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _empacotar(saida: str, encerrou: bool, codigo_de_saida: int) -> str:
    """A mensagem com a saída que vai para o chat."""
    if not encerrou:
        return (f"✅ Saída (programa ainda em execução):\n{saida}" if saida
                else "⏳ Programa em execução mas sem saída nos últimos 5s.")
    mensagem = f"✅ Saída:\n{saida}" if saida else "✅ Programa encerrado sem saída."
    return mensagem + (f"\n\n🔴 Código de saída: {codigo_de_saida}" if codigo_de_saida else "")


_atual = Execucao()


# ── preparar e compilar ──────────────────────────────────────────────────────

def _preparar(codigo: str) -> tuple[str, list[str]]:
    """Tira as crases de markdown, conserta #include e liga o line-buffering do stdout."""
    codigo = codigo.replace("```c", "").replace("```", "").strip()
    codigo = re.sub(r"#include\s*\[([^\]]+)\]", r"#include <\1>", codigo)  # [x.h] -> <x.h>
    codigo, avisos = corrigir_includes(codigo)
    if "setvbuf" not in codigo:
        codigo = re.sub(_INICIO_DO_MAIN, _SETVBUF, codigo, count=1)
    return codigo, avisos


def _compilar(codigo: str) -> subprocess.CompletedProcess:
    with open(_ARQUIVO_C, "w", encoding="utf-8") as arquivo:
        arquivo.write(codigo)
    return subprocess.run(["gcc", _ARQUIVO_C, "-o", _BINARIO, "-Wall", "-lm"],
                          capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)


def _avisos(avisos_include: list[str], avisos_gcc: str = "") -> str:
    texto = "\n".join(avisos_include) + "\n\n" if avisos_include else ""
    return texto + (f"⚠️ Avisos de Compilação:\n{avisos_gcc}\n\n" if avisos_gcc else "")


# ── o que os comandos usam ───────────────────────────────────────────────────

def compilar_e_executar(codigo_c: str, run_id: "str | None" = None) -> str:
    """!run: compila e inicia o programa. A saída chega depois, por verificar_resultado_pendente."""
    global _atual  # pylint: disable=global-statement
    _atual.parar()
    if not codigo_c.replace("```c", "").replace("```", "").strip():
        return "❌ Nenhum código foi enviado após !run."
    codigo, avisos_include = _preparar(codigo_c)
    compilacao = _compilar(codigo)
    if compilacao.returncode != 0:
        return _avisos(avisos_include) + f"❌ Erro de Compilação:\n{compilacao.stderr.strip()}"
    _atual = Execucao(run_id=run_id, codigo=codigo)
    _atual.iniciar()
    return (_avisos(avisos_include, compilacao.stderr.strip())
            + "⏳ Programa em execução e aguardando entrada.\n"
            "Use !r <valor> para enviar input. "
            "A saída será entregue após 5s de silêncio ou quando você usar !kill.")


def enviar_input(valor: str) -> str:
    """!r: manda uma linha para o stdin do programa."""
    if _atual.encerrou:
        return ("⚠️ O programa já encerrou. "
                "Use !kill para ver a saída ou envie !run para um novo código.")
    if not _atual.rodando():
        _atual.parar()
        return "❌ Nenhum programa está aguardando input no momento."
    try:
        _atual.processo.stdin.write(valor.strip() + "\n")
        _atual.processo.stdin.flush()
    except (BrokenPipeError, OSError):
        return "⚠️ O programa encerrou ao receber o input. Aguarde a saída ou use !kill."
    _atual.entradas.append(valor.strip())
    return "⏳ Input enviado. Aguardando próxima entrada ou saída do programa."


def matar_processo() -> str:
    """!kill: encerra o programa e entrega toda a saída que ele deu."""
    if _atual.encerrou or (_atual.processo is None and _atual.pendente):
        pendente = _atual.tirar_pendente()
        _atual.parar()
        return f"✅ Programa já havia encerrado. Saída:\n\n{pendente}" if pendente else NENHUM_PROGRAMA
    if not _atual.rodando():
        pendente = _atual.tirar_pendente()
        _atual.parar()
        return f"🔴 Processo já tinha encerrado. Saída pendente:\n\n{pendente}" if pendente else NENHUM_PROGRAMA
    processo, _atual.processo = _atual.processo, None  # o monitor para de entregar
    _matar(processo)
    time.sleep(0.3)
    _atual.guardar(*_atual.drenar(timeout=0.5))
    partes = [_atual.tirar_pendente(), _atual.tirar_acumulado()]
    _atual.parar()
    pendente, saida = partes
    texto = "\n\n".join(filter(None, [pendente, f"✅ Saída final:\n{saida}" if saida else ""]))
    return f"🔴 Programa encerrado pelo !kill.\n\n{texto}" if texto else \
        "🔴 Programa encerrado pelo !kill. Sem saída adicional."


def verificar_resultado_pendente() -> "str | None":
    """A saída que o monitor deixou pronta (e a apaga); None se não há nada."""
    return _atual.tirar_pendente()


def obter_dados_run() -> "dict | None":
    """Os dados do último !run (código, entradas, saída), para entrar no contexto da IA."""
    if _atual.run_id is None:
        return None
    return {"id": _atual.run_id, "codigo": _atual.codigo,
            "inputs": list(_atual.entradas), "saida": _atual.saida_final}


def esquecer_run() -> None:
    """O !chclear: o último run não volta mais para o contexto."""
    _atual.run_id = None
