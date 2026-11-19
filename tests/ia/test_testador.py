"""O testador de código C que as IAs usam: compila, roda e diz se passou (precisa de gcc)."""

import shutil

import pytest

from bot_moodle.ia import testador

pytestmark = pytest.mark.skipif(not shutil.which("gcc"), reason="precisa de gcc")

DOBRO = '#include <stdio.h>\nint main(void){int n; scanf("%d",&n); printf("%d\\n", n*2); return 0;}'


def test_codigo_certo_passa_e_mostra_a_saida():
    relatorio, passou = testador.testar(DOBRO, ["21\n"])
    assert passou and "42" in relatorio


def test_roda_uma_vez_para_cada_entrada():
    relatorio, _ = testador.testar(DOBRO, ["1\n", "2\n", "3\n"])
    assert "Execução 3" in relatorio and "6" in relatorio


def test_erro_de_compilacao_nao_passa():
    relatorio, passou = testador.testar("int main(void){ return 1 }", [""])
    assert not passou and "Compilação FALHOU" in relatorio


def test_aviso_do_compilador_nao_passa():
    _, passou = testador.testar("int main(void){ int nao_usada; return 0; }", [""])
    assert not passou


def test_codigo_de_saida_diferente_de_zero_nao_passa():
    _, passou = testador.testar("int main(void){ return 3; }", [""])
    assert not passou


def test_acesso_fora_do_vetor_nao_passa():
    # no Linux/macOS o AddressSanitizer acusa; no MinGW (Windows) o programa pode até rodar,
    # então o teste só exige isso onde os sanitizers existem
    estouro = "int main(void){int v[2]; volatile int i=5; v[i]=1; return v[0];}"
    relatorio, passou = testador.testar(estouro, [""])
    if "Sanitizer" in relatorio or "runtime error" in relatorio:
        assert not passou


def test_loop_infinito_estoura_o_tempo(monkeypatch):
    monkeypatch.setattr(testador, "EXEC_TIMEOUT_S", 1)
    relatorio, passou = testador.testar("int main(void){ for(;;); }", [""])
    assert not passou and "passou de 1 s" in relatorio


def test_ferramenta_anota_o_resultado_no_estado():
    estado = {"testou": False, "passou": False}
    relatorio = testador.usar_ferramenta({"codigo": DOBRO, "entradas": ["5\n"]}, estado)
    assert estado == {"testou": True, "passou": True} and "10" in relatorio


def test_ferramenta_limita_a_quantidade_de_entradas():
    estado = {}
    relatorio = testador.usar_ferramenta(
        {"codigo": DOBRO, "entradas": [f"{i}\n" for i in range(50)]}, estado)
    assert f"Execução {testador.MAX_ENTRADAS}" in relatorio
    assert f"Execução {testador.MAX_ENTRADAS + 1}" not in relatorio
