#!/usr/bin/env bash
# Verifica se tudo que o bot precisa está instalado e funcionando; o que faltar, oferece instalar.
# Se estiver tudo certo, sobe o backend. Linux e macOS; no Silverblue, rode dentro da distrobox.
# Compatível com o bash 3.2 do macOS: array vazio vira ${a[@]+"${a[@]}"} por causa do set -u.
set -uo pipefail
SCRIPT=$(readlink -f "$0" 2>/dev/null || echo "$0")  # macOS antigo não tem -f
cd "$(dirname "$SCRIPT")/bot_moodle"
export PATH="$HOME/.local/bin:$PATH"  # onde o instalador do Claude Code coloca o binário

erros=0
instalou=0
ok()    { echo "  ✅ $1"; }
aviso() { echo "  ⚠️  $1"; }

# falta <mensagem> <dica> [comando de instalação]
# Com comando e terminal interativo, pergunta se quer instalar agora.
falta() {
    echo "  ❌ $1"; echo "     → $2"; erros=1
    [ -n "${3:-}" ] && [ -t 0 ] || return 0
    read -r -p "     Instalar agora? [S/n] " r
    case "$r" in [nN]*) return 0 ;; esac
    if bash -c "$3"; then instalou=1; else echo "     ❌ A instalação falhou."; fi
}

# Comando de instalação de pacote do sistema (vazio em sistema imutável/desconhecido)
pacote() {  # pacote <dnf> <apt> <pacman> <comando no macOS>
    if [ "$(uname)" = Darwin ]; then
        case "$4" in brew\ *) command -v brew >/dev/null || return ;; esac
        echo "$4"
    elif command -v rpm-ostree >/dev/null && ! command -v dnf >/dev/null; then return
    elif command -v dnf >/dev/null; then echo "sudo dnf install -y $1"
    elif command -v apt-get >/dev/null; then echo "sudo apt-get install -y $2"
    elif command -v pacman >/dev/null; then echo "sudo pacman -S --noconfirm $3"
    fi
}
dica_pacote() {  # o que mostrar quando não há como instalar automaticamente
    local cmd; cmd=$(pacote "$@")
    if [ -n "$cmd" ]; then echo "$cmd"
    elif [ "$(uname)" = Darwin ]; then echo "instale o Homebrew (https://brew.sh) e rode: $4"
    elif command -v rpm-ostree >/dev/null; then echo "sistema imutável: entre numa distrobox e rode o start.sh lá (dnf install $1)"
    else echo "instale $1 pelo gerenciador de pacotes do sistema"
    fi
}

# --config abre o menu de preferências direto; o resto vai para o bot
config=(); args=()
for a in "$@"; do
    if [ "$a" = --config ]; then config=(--config); else args+=("$a"); fi
done

echo "🔎 Verificando o ambiente..."
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT

# Python
if command -v python3 >/dev/null && python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
    ok "Python $(python3 -c 'import platform; print(platform.python_version())')"
    py_ok=1
else
    falta "Python 3.11+ não encontrado" "$(dica_pacote python3 'python3 python3-venv' python 'brew install python@3.13')" \
          "$(pacote python3 'python3 python3-venv' python 'brew install python@3.13')"
    py_ok=0
fi

# gcc: compila e roda um programa de teste
if ! command -v gcc >/dev/null; then
    falta "gcc não encontrado (necessário para !run e para a IA testar código)" \
          "$(dica_pacote gcc gcc gcc 'xcode-select --install')" \
          "$(pacote gcc gcc gcc 'xcode-select --install')"
else
    printf '#include <stdio.h>\nint main(void){puts("ok");return 0;}\n' > "$tmp/t.c"
    if gcc "$tmp/t.c" -o "$tmp/t" 2>"$tmp/gcc.log" && [ "$("$tmp/t")" = "ok" ]; then
        ok "gcc compila e executa"
    else
        falta "gcc não conseguiu compilar/rodar um programa de teste: $(head -1 "$tmp/gcc.log")" \
              "$(dica_pacote 'gcc glibc-devel' build-essential base-devel 'xcode-select --install')" \
              "$(pacote 'gcc glibc-devel' build-essential base-devel 'xcode-select --install')"
    fi
fi

# .venv e dependências Python (cria/instala sozinho)
deps_ok=0
if [ "$py_ok" = 1 ]; then
    deps='import flask, flask_cors, duckdb, dotenv, instagrapi, anthropic, certifi; from google import genai'
    if ! { [ -x .venv/bin/bot-moodle ] && .venv/bin/python -c "$deps" 2>/dev/null; }; then
        echo "  📦 Preparando .venv e instalando dependências..."
        { [ -d .venv ] || python3 -m venv .venv; } && .venv/bin/pip install -q -e . >"$tmp/pip.log" 2>&1
    fi
    if [ -x .venv/bin/bot-moodle ] && .venv/bin/python -c "$deps" 2>/dev/null; then
        ok "Dependências Python"; deps_ok=1
    else
        falta "Falha ao instalar as dependências: $(tail -1 "$tmp/pip.log" 2>/dev/null)" \
              "apague bot_moodle/.venv e rode de novo; no Debian/Ubuntu: $(dica_pacote python3 python3-venv python 'brew install python@3.13')"
    fi
fi

# Menu de preferências (IAs, modelos, plataformas, vigia): Enter mantém as salvas
if [ "$deps_ok" = 1 ]; then
    echo
    .venv/bin/python -m bot_moodle.preferencias ${config[@]+"${config[@]}"}
    echo
    # Testa cada IA da linha (uma mensagem por IA), o Instagram e a porta, conforme as escolhas
    while read -r st msg; do
        case "$st" in
            OK)    ok "$msg" ;;
            AVISO) aviso "$msg" ;;
            PULA)  echo "  ➖ $msg" ;;
            ERRO)  echo "  ❌ $msg"; erros=1 ;;
            DICA)  echo "     → $msg" ;;
            *Error:) echo "  ❌ as checagens quebraram: $st $msg"; erros=1 ;;  # fim de um traceback
            *)     ;;  # o resto do traceback e avisos de bibliotecas
        esac
    done < <(.venv/bin/python -m bot_moodle.checagens 2>&1)
fi

if [ "$instalou" = 1 ]; then
    echo; echo "📦 Instalado. Verificando de novo..."; echo
    rm -rf "$tmp"
    exec "$SCRIPT" ${config[@]+"${config[@]}"} ${args[@]+"${args[@]}"}
fi
if [ "$erros" -ne 0 ]; then
    echo; echo "❌ Corrija os itens acima e rode o start.sh de novo."
    exit 1
fi
echo; echo "🚀 Tudo certo. Subindo o bot..."
exec .venv/bin/bot-moodle ${args[@]+"${args[@]}"}
