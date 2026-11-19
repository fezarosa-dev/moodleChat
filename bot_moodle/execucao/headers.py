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


_INCLUDE_COMPLETO = re.compile(r'#include\s*[<"]([^>"]+)[>"]')
_INCLUDE_VAZIO = re.compile(r"#include\s*")


def _headers_presentes(linhas: list[str]) -> set[str]:
    return {m.group(1) for linha in linhas if (m := _INCLUDE_COMPLETO.match(linha.strip()))}


def _headers_necessarios(codigo: str, presentes: set[str]) -> list[str]:
    """Os headers que o código usa e ainda não inclui; sem nenhuma pista, stdio.h."""
    necessarios = [header for padrao, header in _HEADERS_INFERIDOS
                   if header not in presentes and re.search(padrao, codigo)]
    return necessarios or ["stdio.h"]


def corrigir_includes(codigo: str) -> tuple[str, list[str]]:
    """Troca cada linha "#include" vazia (o chat do Moodle apaga o <header.h>) pelos headers que o
    código usa. A última linha vazia recebe os headers que sobrarem; as vazias a mais somem.

    Retorna (código corrigido, avisos).
    """
    linhas = codigo.split("\n")
    vazias = [i for i, linha in enumerate(linhas) if _INCLUDE_VAZIO.fullmatch(linha.strip())]
    if not vazias:
        return codigo, []
    necessarios = _headers_necessarios(codigo, _headers_presentes(linhas))
    # um header por linha vazia; a última leva todos os que sobram
    grupos = [necessarios[i:i + 1] for i in range(len(vazias) - 1)] + [necessarios[len(vazias) - 1:]]
    for indice, grupo in zip(vazias, grupos):
        linhas[indice] = "\n".join(f"#include <{header}>" for header in grupo)
    aviso = (f"⚠️ Aviso: {len(vazias)} diretiva(s) '#include' incompleta(s) detectada(s) "
             f"(provavelmente removidas pelo chat). "
             f"Inferido(s) automaticamente: {', '.join(necessarios)}.")
    return "\n".join(linhas), [aviso]
