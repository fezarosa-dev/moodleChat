@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
rem Verifica se tudo que o bot precisa está instalado e funcionando; se estiver, sobe o backend.
set PYTHONUTF8=1
cd /d "%~dp0"
set ERROS=0
rem --config abre o menu de preferências direto
set "CONFIG="
if /i "%~1"=="--config" set "CONFIG=--config"
set INSTALOU=0
set "TMPD=%TEMP%\bot_moodle_check"
if not exist "%TMPD%" mkdir "%TMPD%"

echo Verificando o ambiente...
rem Estrutura antiga (bot_moodle\bot_moodle, até a v0.1): leva o .env, o banco e as sessões do
rem Instagram para o lugar novo (.env na raiz, o resto em dados\). Nunca sobrescreve nada.
if exist "bot_moodle\.env" if not exist ".env" move "bot_moodle\.env" ".env" >nul && echo   .env movido para a raiz do projeto
for %%F in (bot_moodle\ig_session*.json bot_moodle\moodle_history.duckdb*) do (
    if not exist dados mkdir dados
    if not exist "dados\%%~nxF" move "%%~F" dados\ >nul && echo   %%~nxF movido para dados\
)
if exist "bot_moodle\.venv" rd /s /q "bot_moodle\.venv"
if exist "bot_moodle\bot_moodle.egg-info" rd /s /q "bot_moodle\bot_moodle.egg-info"

rem ── Python 3.11+ ──────────────────────────────────────────────
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if defined PY %PY% -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>nul || set "PY="
if defined PY (echo   [OK] Python) else (call :falta "Python 3.11+ não encontrado" "winget install Python.Python.3.13" python)

rem ── gcc: compila e roda um programa de teste ─────────────────
where gcc >nul 2>nul || (call :falta "gcc não encontrado, necessário para executar código C" "winget install BrechtSanders.WinLibs.POSIX.UCRT" gcc & goto :deps)
>"%TMPD%\t.c" echo #include ^<stdio.h^>
>>"%TMPD%\t.c" echo int main(void){puts("ok");return 0;}
gcc "%TMPD%\t.c" -o "%TMPD%\t.exe" 2>"%TMPD%\gcc.log" || (call :falta "gcc não compilou um programa de teste" "veja o erro em %TMPD%\gcc.log ou reinstale o gcc" & goto :deps)
set "SAIDA="
for /f "delims=" %%L in ('"%TMPD%\t.exe"') do set "SAIDA=%%L"
if "!SAIDA!"=="ok" (echo   [OK] gcc compila e executa) else (call :falta "o programa de teste compilou mas não rodou" "reinstale o gcc")

rem ── .venv e dependências Python: cria/instala sozinho ────────
:deps
if not defined PY goto :fim
set "DEPS=import flask, flask_cors, duckdb, dotenv, instagrapi, anthropic, certifi; from google import genai"
if exist ".venv\Scripts\bot-moodle.exe" ".venv\Scripts\python.exe" -c "%DEPS%" >nul 2>nul && goto :deps_ok
echo   Preparando .venv e instalando dependências...
if not exist ".venv\Scripts\python.exe" %PY% -m venv .venv
".venv\Scripts\python.exe" -m pip install -q -e . >"%TMPD%\pip.log" 2>&1
if exist ".venv\Scripts\bot-moodle.exe" ".venv\Scripts\python.exe" -c "%DEPS%" >nul 2>nul && goto :deps_ok
call :falta "falha ao instalar as dependências" "veja %TMPD%\pip.log; apague a pasta .venv e rode de novo"
goto :fim
:deps_ok
echo   [OK] Dependências Python

rem ── Menu de preferências (IAs, modelos, plataformas, vigia): Enter mantém as salvas
echo.
".venv\Scripts\python.exe" -m bot_moodle.inicio.preferencias %CONFIG%
echo.

rem ── Testa cada IA da linha (uma mensagem por IA), o Instagram e a porta ──
echo Testando as IAs da linha, o Instagram e a porta (pode levar um minuto)...
".venv\Scripts\python.exe" -m bot_moodle.inicio.checagens >"%TMPD%\checagens.log" 2>&1
rem sem expansão atrasada no laço: com ela, um "!" das mensagens (ex.: !run) some
setlocal DisableDelayedExpansion
for /f "usebackq tokens=1*" %%A in ("%TMPD%\checagens.log") do (
    if "%%A"=="OK" echo   [OK] %%B
    if "%%A"=="AVISO" echo   [AVISO] %%B
    if "%%A"=="PULA" echo   [--] %%B
    if "%%A"=="DICA" echo          -^> %%B
    if "%%A"=="ERRO" echo   [ERRO] %%B
)
endlocal
findstr /b /c:"ERRO " "%TMPD%\checagens.log" >nul && set ERROS=1
rem traceback de um erro inesperado nas checagens
findstr /r /c:"^[A-Za-z.]*Error:" "%TMPD%\checagens.log" >nul && (
    echo   [ERRO] as checagens quebraram:
    findstr /r /c:"^[A-Za-z.]*Error:" "%TMPD%\checagens.log"
    set ERROS=1
)

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
where winget >nul 2>nul || exit /b 0
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
