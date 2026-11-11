#!/usr/bin/env bash
# Verifica se tudo que o bot precisa está instalado e funcionando; se estiver, sobe o backend.
# Rode no ambiente onde estão gcc e claude (no Silverblue: dentro da distrobox).
set -uo pipefail
cd "$(dirname "$(readlink -f "$0")")/bot_moodle"

erros=0
ok()    { echo "  ✅ $1"; }
aviso() { echo "  ⚠️  $1"; }
falta() { echo "  ❌ $1"; echo "     → $2"; erros=1; }

# Comando de instalação conforme o gerenciador de pacotes do sistema
instalar() {
    if command -v rpm-ostree >/dev/null && ! command -v dnf >/dev/null; then
        echo "sistema imutável: crie/entre numa distrobox e instale lá (dnf install $1)"
    elif command -v dnf >/dev/null; then echo "sudo dnf install $1"
    elif command -v apt >/dev/null; then echo "sudo apt install $2"
    elif command -v pacman >/dev/null; then echo "sudo pacman -S $3"
    else echo "instale $1 pelo gerenciador de pacotes do sistema"
    fi
}

echo "🔎 Verificando o ambiente..."
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT

# Python
if command -v python3 >/dev/null && python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
    ok "Python $(python3 -c 'import platform; print(platform.python_version())')"
    py_ok=1
else
    falta "Python 3.11+ não encontrado" "$(instalar python3 'python3 python3-venv' python)"
    py_ok=0
fi

# gcc: compila e roda um programa de teste
if ! command -v gcc >/dev/null; then
    falta "gcc não encontrado (necessário para !run e para a IA testar código)" "$(instalar gcc gcc gcc)"
else
    printf '#include <stdio.h>\nint main(void){puts("ok");return 0;}\n' > "$tmp/t.c"
    if gcc "$tmp/t.c" -o "$tmp/t" 2>"$tmp/gcc.log" && [ "$("$tmp/t")" = "ok" ]; then
        ok "gcc compila e executa"
    else
        falta "gcc não conseguiu compilar/rodar um programa de teste: $(head -1 "$tmp/gcc.log")" \
              "$(instalar 'gcc glibc-devel' 'build-essential' 'base-devel')"
    fi
fi

# Claude Code: instalado e logado (pergunta mínima, usa um pouco da cota)
if ! command -v claude >/dev/null; then
    falta "Claude Code não encontrado" "curl -fsSL https://claude.ai/install.sh | bash   (depois rode: claude e faça login)"
else
    resp=$(cd "$tmp" && timeout 90 claude -p --model haiku --tools "" --setting-sources "" \
           --strict-mcp-config --no-session-persistence "Responda apenas: ok" 2>&1)
    if [ $? -eq 0 ] && [ -n "$resp" ]; then
        ok "Claude Code responde"
    else
        falta "Claude Code não respondeu: $(echo "$resp" | head -1)" "rode: claude   e faça login"
    fi
fi

# .venv e dependências Python (cria/instala sozinho)
if [ "$py_ok" = 1 ]; then
    deps='import flask, flask_cors, duckdb, dotenv; from google import genai'
    if ! { [ -x .venv/bin/bot-moodle ] && .venv/bin/python -c "$deps" 2>/dev/null; }; then
        echo "  📦 Preparando .venv e instalando dependências..."
        { [ -d .venv ] || python3 -m venv .venv; } && .venv/bin/pip install -q -e . >"$tmp/pip.log" 2>&1
    fi
    if [ -x .venv/bin/bot-moodle ] && .venv/bin/python -c "$deps" 2>/dev/null; then
        ok "Dependências Python"
    else
        falta "Falha ao instalar as dependências: $(tail -1 "$tmp/pip.log" 2>/dev/null)" \
              "apague bot_moodle/.venv e rode de novo; no Debian/Ubuntu: $(instalar python3 python3-venv python)"
    fi
fi

# .env (opcional)
if [ ! -f .env ]; then
    aviso ".env não encontrado: usando padrões, sem Gemini de reserva (cp .env.example .env)"
elif ! grep -qE '^API_KEY=.+' .env || grep -qE '^API_KEY=sua_chave_aqui' .env; then
    aviso "API_KEY não configurada no .env: sem Gemini de reserva (opcional)"
else
    ok ".env com Gemini de reserva"
fi

# Porta livre
porta=${PORT:-$(grep -E '^PORT=' .env 2>/dev/null | cut -d= -f2)}
porta=${porta:-5000}
if [ "$py_ok" = 1 ] && ! python3 -c "import socket; socket.create_server(('127.0.0.1', $porta)).close()" 2>/dev/null; then
    falta "Porta $porta já está em uso (o bot já está rodando?)" "feche o outro processo ou mude PORT no .env"
else
    ok "Porta $porta livre"
fi
[ "$porta" = 5000 ] || aviso "A extensão espera a porta 5000 (BACKEND_URL em chatUsage.js)"

if [ "$erros" -ne 0 ]; then
    echo; echo "❌ Corrija os itens acima e rode o start.sh de novo."
    exit 1
fi
echo; echo "🚀 Tudo certo. Subindo o bot..."
exec .venv/bin/bot-moodle "$@"
