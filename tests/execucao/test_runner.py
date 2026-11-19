"""!run, !r e !kill: compilar, rodar com entrada interativa e entregar a saída (precisa de gcc).

O comando está desativado no chat (RUN_ATIVO = False), mas o código continua e é testado aqui.
"""

import shutil
import time

import pytest

from bot_moodle import comandos
from bot_moodle.execucao import runner

pytestmark = pytest.mark.skipif(not shutil.which("gcc"), reason="precisa de gcc")

DOBRO = '#include <stdio.h>\nint main(){int x; scanf("%d",&x); printf("dobro=%d\\n", x*2);}'


def esperar_saida(segundos=15.0):
    """A saída chega depois de SILENCE_TIMEOUT sem novidade, ou quando o programa termina."""
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        saida = runner.verificar_resultado_pendente()
        if saida:
            return saida
        time.sleep(0.1)
    return None


def esperar(condicao, segundos=10.0):
    """Espera a condição ficar verdadeira (sem tempo fixo: o macOS do CI demora a abrir um
    binário recém-compilado)."""
    limite = time.monotonic() + segundos
    while not condicao() and time.monotonic() < limite:
        time.sleep(0.05)


def test_programa_recebe_entrada_depois_do_run():
    assert "aguardando entrada" in runner.compilar_e_executar(DOBRO)
    runner.enviar_input("21")
    assert "dobro=42" in esperar_saida()


def test_saida_de_programa_que_terminou_sozinho_e_guardada_para_o_contexto():
    runner.compilar_e_executar(DOBRO, run_id="7")
    runner.enviar_input("5")
    esperar_saida()
    assert runner.obter_dados_run() == {"id": "7", "codigo": runner.obter_dados_run()["codigo"],
                                        "inputs": ["5"], "saida": "dobro=10"}


def test_include_apagado_pelo_chat_e_reconstruido():
    # "#include" vazio = o que sobra quando o chat do Moodle apaga o <stdio.h>
    resposta = runner.compilar_e_executar(DOBRO.replace("<stdio.h>", ""))
    assert "Inferido(s) automaticamente: stdio.h" in resposta and "aguardando entrada" in resposta


def test_include_com_colchetes_vira_include_normal():
    resposta = runner.compilar_e_executar(DOBRO.replace("<stdio.h>", "[stdio.h]"))
    assert "Erro de Compilação" not in resposta


def test_erro_de_compilacao_mostra_o_gcc():
    assert "❌ Erro de Compilação" in runner.compilar_e_executar("int main(){ return 1 }")


def test_run_sem_codigo():
    assert "Nenhum código" in runner.compilar_e_executar("```c\n```")


def test_r_sem_programa_rodando():
    assert "Nenhum programa" in runner.enviar_input("5")


def test_kill_sem_programa_rodando():
    assert "Nenhum programa estava em execução" in runner.matar_processo()


def test_kill_entrega_a_saida_de_programa_em_loop():
    runner.compilar_e_executar('#include <stdio.h>\nint main(){ puts("começou"); for(;;); }')
    esperar(lambda: runner._atual.ultimo_print > 0)  # o programa já escreveu algo
    resposta = runner.matar_processo()
    assert "encerrado pelo !kill" in resposta and "começou" in resposta


def test_kill_entrega_saida_de_programa_ja_encerrado(enviar, monkeypatch):
    monkeypatch.setattr(comandos, "RUN_ATIVO", True)
    enviar(f"!run {DOBRO}")
    enviar("!r 21")
    esperar(lambda: runner._atual.encerrou)  # o programa termina sozinho e a saída fica pendente
    assert "dobro=42" in enviar("!kill")["resposta"]


def test_run_logo_depois_do_kill_nao_e_confundido_com_o_anterior():
    """Bug antigo: depois do !kill, o monitor do programa morto ainda lia a saída por ~0,8 s e,
    com um !run logo em seguida, marcava o programa novo como encerrado (código -9)."""
    runner.compilar_e_executar(DOBRO)  # fica esperando a entrada
    time.sleep(0.3)
    runner.matar_processo()
    runner.compilar_e_executar(DOBRO)
    time.sleep(1.0)
    assert "Input enviado" in runner.enviar_input("21")
    assert "dobro=42" in esperar_saida()
