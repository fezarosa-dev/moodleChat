"""!run + !r: o programa precisa continuar recebendo entrada depois que !run responde."""

import shutil
import time

import pytest

from bot_moodle.core import runner


@pytest.mark.skipif(not shutil.which("gcc"), reason="precisa de gcc")
def test_run_recebe_input():
    # "#include" vazio = o que sobra quando o chat do Moodle apaga o <stdio.h>
    codigo = '#include\nint main(){int x; scanf("%d",&x); printf("dobro=%d\\n", x*2);}'
    assert "aguardando entrada" in runner.compilar_e_executar(codigo)
    runner.enviar_input("21")
    for _ in range(80):  # até ~8s (saída sai após SILENCE_TIMEOUT ou no fim do programa)
        saida = runner.verificar_resultado_pendente()
        if saida:
            break
        time.sleep(0.1)
    assert saida and "dobro=42" in saida
