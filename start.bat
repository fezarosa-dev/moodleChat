@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
rem Verifica se tudo que o bot precisa está instalado e funcionando; se estiver, sobe o backend.
set PYTHONUTF8=1
cd /d "%~dp0bot_moodle"
set ERROS=0
set INSTALOU=0
set "TMPD=%TEMP%\bot_moodle_check"
if not exist "%TMPD%" mkdir "%TMPD%"

echo Verificando o ambiente...

rem ── Python 3.11+ ──────────────────────────────────────────────
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if defined PY %PY% -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>nul || set "PY="
if defined PY (echo   [OK] Python) else (call :falta "Python 3.11+ não encontrado" "winget install Python.Python.3.13" python)

rem ── gcc: compila e roda um programa de teste ─────────────────
where gcc >nul 2>nul || (call :falta "gcc não encontrado, necessário para executar código C" "winget install BrechtSanders.WinLibs.POSIX.UCRT" gcc & goto :claude)
>"%TMPD%\t.c" echo #include ^<stdio.h^>
>>"%TMPD%\t.c" echo int main(void){puts("ok");return 0;}
gcc "%TMPD%\t.c" -o "%TMPD%\t.exe" 2>"%TMPD%\gcc.log" || (call :falta "gcc não compilou um programa de teste" "veja o erro em %TMPD%\gcc.log ou reinstale o gcc" & goto :claude)
set "SAIDA="
for /f "delims=" %%L in ('"%TMPD%\t.exe"') do set "SAIDA=%%L"
if "!SAIDA!"=="ok" (echo   [OK] gcc compila e executa) else (call :falta "o programa de teste compilou mas não rodou" "reinstale o gcc")

rem ── Claude Code: instalado e logado ──────────────────────────
:claude
where claude >nul 2>nul || (call :falta "Claude Code não encontrado" "no PowerShell: irm https://claude.ai/install.ps1 | iex   depois rode claude e faça login" claude & goto :deps)
where git >nul 2>nul || (call :falta "Git for Windows não encontrado, o Claude Code precisa do Git Bash" "winget install Git.Git" git & goto :deps)
pushd "%TMPD%"
call claude -p --model haiku --tools "" --setting-sources "" --strict-mcp-config --no-session-persistence "Responda apenas: ok" >"%TMPD%\claude.log" 2>&1
set "CLAUDE_ERRO=!errorlevel!"
popd
set "RESP="
set /p RESP=<"%TMPD%\claude.log"
if "!CLAUDE_ERRO!"=="0" if defined RESP (echo   [OK] Claude Code responde& goto :deps)
call :falta "Claude Code não respondeu: !RESP!" "rode claude e faça login"

rem ── .venv e dependências Python: cria/instala sozinho ────────
:deps
if not defined PY goto :env
set "DEPS=import flask, flask_cors, duckdb, dotenv; from google import genai"
if exist ".venv\Scripts\bot-moodle.exe" ".venv\Scripts\python.exe" -c "%DEPS%" >nul 2>nul && goto :deps_ok
echo   Preparando .venv e instalando dependências...
if not exist ".venv\Scripts\python.exe" %PY% -m venv .venv
".venv\Scripts\python.exe" -m pip install -q -e . >"%TMPD%\pip.log" 2>&1
if exist ".venv\Scripts\bot-moodle.exe" ".venv\Scripts\python.exe" -c "%DEPS%" >nul 2>nul && goto :deps_ok
call :falta "falha ao instalar as dependências" "veja %TMPD%\pip.log; apague bot_moodle\.venv e rode de novo"
goto :env
:deps_ok
echo   [OK] Dependências Python

rem ── .env: opcional ───────────────────────────────────────────
:env
if not exist ".env" (echo   [AVISO] .env não encontrado: usando padrões, sem Gemini de reserva& goto :porta)
findstr /r "^API_KEY=." .env >nul || goto :sem_key
findstr /c:"API_KEY=sua_chave_aqui" .env >nul && goto :sem_key
echo   [OK] .env com Gemini de reserva
goto :porta
:sem_key
echo   [AVISO] API_KEY não configurada no .env: sem Gemini de reserva, é opcional

rem ── Porta livre ──────────────────────────────────────────────
:porta
set "PORTA=%PORT%"
if not defined PORTA if exist ".env" for /f "tokens=2 delims==" %%P in ('findstr /r "^PORT=" .env') do set "PORTA=%%P"
if not defined PORTA set "PORTA=5000"
if not defined PY goto :fim
%PY% -c "import socket; socket.create_server(('127.0.0.1', !PORTA!)).close()" >nul 2>nul
if errorlevel 1 (call :falta "Porta !PORTA! já está em uso, o bot já está rodando?" "feche o outro processo ou mude PORT no .env") else (echo   [OK] Porta !PORTA! livre)
if not "!PORTA!"=="5000" echo   [AVISO] A extensão espera a porta 5000, veja BACKEND_URL em chatUsage.js

:fim
rd /s /q "%TMPD%" 2>nul
echo.
if "!INSTALOU!"=="1" (
    echo Instalado. Feche este terminal, abra um novo e rode o start.bat de novo.
    echo O Windows só atualiza o PATH em terminais novos.
    pause
    exit /b 1
)
if "!ERROS!"=="1" (
    echo Corrija os itens acima e rode o start.bat de novo.
    pause
    exit /b 1
)
echo Tudo certo. Subindo o bot...
".venv\Scripts\bot-moodle.exe" %*
if errorlevel 1 pause
exit /b

:falta
set "M1=%~1"
set "M2=%~2"
echo   [ERRO] !M1!
echo          -^> !M2!
set ERROS=1
rem 3º argumento: o que instalar; pergunta antes
if "%~3"=="" exit /b 0
if not "%~3"=="claude" (where winget >nul 2>nul || exit /b 0)
set "R="
set /p "R=         Instalar agora? [S/n] "
if /i "!R!"=="n" exit /b 0
call :instalar_%~3
if errorlevel 1 (echo          A instalação falhou.) else (set INSTALOU=1)
exit /b 0

:instalar_python
winget install -e --id Python.Python.3.13 --accept-source-agreements --accept-package-agreements
exit /b

:instalar_gcc
winget install -e --id BrechtSanders.WinLibs.POSIX.UCRT --accept-source-agreements --accept-package-agreements
exit /b

:instalar_git
winget install -e --id Git.Git --accept-source-agreements --accept-package-agreements
exit /b

:instalar_claude
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://claude.ai/install.ps1 | iex"
exit /b
