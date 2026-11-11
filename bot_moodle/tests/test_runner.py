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


@pytest.mark.skipif(not shutil.which("gcc"), reason="precisa de gcc")
def test_kill_entrega_saida_de_programa_ja_encerrado(tmp_path, monkeypatch):
    from flask import Flask  # pylint: disable=import-outside-toplevel
    from bot_moodle import db  # pylint: disable=import-outside-toplevel
    from bot_moodle.routes import chat  # pylint: disable=import-outside-toplevel

    monkeypatch.setattr(chat, "RUN_ATIVO", True)
    app = Flask(__name__)
    app.register_blueprint(chat.bp)
    chat.init_handlers(db.conectar(str(tmp_path / "t.duckdb")), None)
    cli = app.test_client()

    def enviar(i, texto):
        return cli.post("/check_and_save", json={"id": i, "texto": texto}).json

    enviar("1", '!run #include <stdio.h>\nint main(){int x; scanf("%d",&x); printf("dobro=%d\\n", x*2);}')
    enviar("2", "!r 21")
    time.sleep(1)  # programa termina sozinho; saída fica pendente
    assert "dobro=42" in enviar("3", "!kill")["resposta"]
