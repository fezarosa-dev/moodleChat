"""Inferência automática de diretivas #include para código C."""

import re

# Mapeamento padrão regex → header necessário (ordem importa: mais específico primeiro)
_HEADERS_INFERIDOS: list[tuple[str, str]] = [
    (
        r"\bprintf\b|\bscanf\b|\bputchar\b|\bgetchar\b|\bputs\b|\bgets\b"
        r"|\bfopen\b|\bfclose\b|\bfprintf\b|\bfscanf\b|\bfflush\b|\bperror\b"
        r"|\bfread\b|\bfwrite\b|\bfseek\b|\bftell\b|\brewind\b|\bfeof\b"
        r"|\bsscanf\b|\bsprintf\b|\bsnprintf\b|\bvprintf\b|\bgetline\b"
        r"|\bfgets\b|\bfputs\b",
        "stdio.h",
    ),
    (
        r"\bmalloc\b|\bcalloc\b|\brealloc\b|\bfree\b|\bexit\b|\babort\b"
        r"|\batoi\b|\batof\b|\batol\b|\batoll\b|\bstrtol\b|\bstrtod\b"
        r"|\bstrtof\b|\brand\b|\bsrand\b|\babs\b|\bdiv\b|\bqsort\b"
        r"|\bbsearch\b|\bgetenv\b|\bsystem\b|\bNULL\b|\bsize_t\b",
        "stdlib.h",
    ),
    (
        r"\bstrlen\b|\bstrcpy\b|\bstrncpy\b|\bstrcat\b|\bstrncat\b"
        r"|\bstrcmp\b|\bstrncmp\b|\bstrchr\b|\bstrrchr\b|\bstrstr\b"
        r"|\bstrtok\b|\bstrdup\b|\bmemset\b|\bmemcpy\b|\bmemmove\b|\bmemcmp\b",
        "string.h",
    ),
    (
        r"\bsqrt\b|\bpow\b|\bfabs\b|\bceil\b|\bfloor\b|\bround\b|\btrunc\b"
        r"|\bsin\b|\bcos\b|\btan\b|\basin\b|\bacos\b|\batan\b|\batan2\b"
        r"|\blog\b|\blog2\b|\blog10\b|\bexp\b|\bexp2\b|\bhypot\b|\bfmod\b"
        r"|\bM_PI\b|\bINFINITY\b|\bNAN\b|\bisnan\b|\bisinf\b",
        "math.h",
    ),
    (
        r"\bisalpha\b|\bisdigit\b|\bisspace\b|\bisupper\b|\bislower\b"
        r"|\btoupper\b|\btolower\b|\bisalnum\b|\bispunct\b|\bisprint\b"
        r"|\bisblank\b|\biscntrl\b|\bisxdigit\b",
        "ctype.h",
    ),
    (
        r"\btime\b|\bclock\b|\bdifftime\b|\bmktime\b|\blocaltime\b"
        r"|\bgmtime\b|\bstrftime\b|\btime_t\b|\bstruct\s+tm\b|\bclock_t\b",
        "time.h",
    ),
    (
        r"\bINT_MAX\b|\bINT_MIN\b|\bUINT_MAX\b|\bLONG_MAX\b|\bLONG_MIN\b"
        r"|\bSHRT_MAX\b|\bCHAR_MAX\b|\bUCHAR_MAX\b|\bULONG_MAX\b",
        "limits.h",
    ),
    (
        r"\bFLT_MAX\b|\bFLT_MIN\b|\bDBL_MAX\b|\bDBL_MIN\b"
        r"|\bFLT_EPSILON\b|\bDBL_EPSILON\b",
        "float.h",
    ),
    (
        r"\bint8_t\b|\bint16_t\b|\bint32_t\b|\bint64_t\b"
        r"|\buint8_t\b|\buint16_t\b|\buint32_t\b|\buint64_t\b"
        r"|\bintptr_t\b|\buintptr_t\b|\bPRId32\b|\bPRIu64\b",
        "stdint.h",
    ),
    (r"\bbool\b|\btrue\b|\bfalse\b", "stdbool.h"),
    (r"\bassert\b", "assert.h"),
    (
        r"\bsignal\b|\braise\b|\bSIGINT\b|\bSIGSEGV\b"
        r"|\bSIGTERM\b|\bSIG_DFL\b",
        "signal.h",
    ),
    (r"\bsetjmp\b|\blongjmp\b|\bjmp_buf\b", "setjmp.h"),
    (r"\bva_list\b|\bva_start\b|\bva_arg\b|\bva_end\b|\bva_copy\b", "stdarg.h"),
    (r"\berrno\b|\bERANGE\b|\bEDOM\b|\bENOMEM\b|\bEINVAL\b", "errno.h"),
    (
        r"\bsetlocale\b|\blocaleconv\b|\bLC_ALL\b|\bLC_NUMERIC\b|\bLC_TIME\b",
        "locale.h",
    ),
]


def corrigir_includes(codigo: str) -> tuple[str, list[str]]:
    """
    Detecta linhas '#include' sem biblioteca e as substitui pelos headers
    inferidos pelo conteúdo do código.

    Retorna (codigo_corrigido, lista_de_avisos).
    """
    linhas = codigo.split("\n")
    avisos: list[str] = []
    presentes: set[str] = set()
    indices_vazios: list[int] = []

    for i, linha in enumerate(linhas):
        s = linha.strip()
        if s.startswith("#include") and ("<" in s or '"' in s):
            m = re.search(r'[<"]([^>"]+)[>"]', s)
            if m:
                presentes.add(m.group(1))
        elif re.match(r"^#include\s*$", s):
            indices_vazios.append(i)

    if not indices_vazios:
        return codigo, avisos

    necessarios = [
        h
        for p, h in _HEADERS_INFERIDOS
        if h not in presentes and re.search(p, codigo)
    ]
    if not necessarios:
        necessarios = ["stdio.h"]

    qtd = len(indices_vazios)
    avisos.append(
        f"⚠️ Aviso: {qtd} diretiva(s) '#include' incompleta(s) detectada(s) "
        f"(provavelmente removidas pelo chat). "
        f"Inferido(s) automaticamente: {', '.join(necessarios)}."
    )

    for idx, linha_idx in enumerate(indices_vazios):
        if idx >= len(necessarios):
            linhas[linha_idx] = ""
        elif idx == len(indices_vazios) - 1 and len(necessarios) > qtd:
            extras = necessarios[idx:]
            linhas[linha_idx] = "\n".join(f"#include <{h}>" for h in extras)
        else:
            linhas[linha_idx] = f"#include <{necessarios[idx]}>"

    return "\n".join(linhas), avisos
