"""Reconstrução dos #include que o chat do Moodle apaga (sobra só "#include")."""

from bot_moodle.execucao.headers import corrigir_includes


def test_codigo_com_includes_completos_nao_muda():
    codigo = "#include <stdio.h>\nint main(void){ printf(\"oi\"); }"
    assert corrigir_includes(codigo) == (codigo, [])


def test_include_vazio_vira_o_header_que_o_codigo_usa():
    codigo, avisos = corrigir_includes("#include\nint main(void){ printf(\"oi\"); }")
    assert codigo.startswith("#include <stdio.h>\n")
    assert "1 diretiva(s)" in avisos[0] and "stdio.h" in avisos[0]


def test_ultimo_include_vazio_recebe_os_headers_que_sobram():
    codigo, _ = corrigir_includes(
        "#include\n#include\nint main(void){ char *s = malloc(9); printf(\"%zu\", strlen(s)); }")
    assert codigo.split("\nint main")[0] == (
        "#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>")


def test_header_ja_presente_nao_e_repetido():
    codigo, _ = corrigir_includes("#include <stdio.h>\n#include\nint main(void){ printf(\"%d\", abs(-1)); }")
    assert codigo.count("stdio.h") == 1 and "#include <stdlib.h>" in codigo


def test_sem_pista_no_codigo_usa_stdio():
    codigo, _ = corrigir_includes("#include\nint main(void){ return 0; }")
    assert codigo.startswith("#include <stdio.h>")


def test_includes_vazios_a_mais_viram_linhas_em_branco():
    codigo, _ = corrigir_includes("#include\n#include\n#include\nint main(void){ printf(\"oi\"); }")
    assert codigo == "#include <stdio.h>\n\n\nint main(void){ printf(\"oi\"); }"


def test_reconhece_math_e_ctype():
    codigo, _ = corrigir_includes("#include\nint main(void){ return (int)sqrt(toupper('a')); }")
    assert "#include <math.h>" in codigo and "#include <ctype.h>" in codigo
