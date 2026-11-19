# Moodle Chat Bot — Assistente Acadêmico de Programação

Backend local (com ou sem extensão de navegador) que transforma o chat do Moodle num assistente de programação:
compila e executa código C pelo próprio chat e conversa com uma IA (Claude Code logado na máquina,
Gemini como reserva) para tirar dúvidas e corrigir código.

## Como funciona

Há dois jeitos de falar com o Moodle, escolhidos no menu do start:

- **Pela API (padrão, sem extensão):** o backend usa a API oficial do Moodle (a mesma do app do celular)
  com a chave `MOODLE_TOKEN`, olha as suas conversas a cada ~5 s e responde na mesma conversa. Veja
  [Moodle pela API](#moodle-pela-api-sem-extensão).
- **Pela extensão:** o jeito antigo, descrito abaixo.

1. A extensão (`content.js` / `chatUsage.js`) lê o chat do Moodle a cada 2 s e envia cada mensagem
   nova para o backend em `http://localhost:5000/check_and_save`.
2. O backend (Flask + DuckDB) identifica comandos (`!chat`, `!fix`…), executa e devolve a resposta.
3. A extensão escreve a resposta no chat, quebrando em várias mensagens quando passa do limite do Moodle.

Mensagens que não começam com `!` são só registradas, sem resposta.

## Requisitos

| | Linux | macOS | Windows |
|---|---|---|---|
| Python 3.11+ | pacote `python3` (+ `python3-venv` no Debian/Ubuntu) | `brew install python@3.13` | `winget install Python.Python.3.13` |
| GCC (para a IA compilar e testar o código) | pacote `gcc` | `xcode-select --install` (o `gcc` é o clang) | MinGW: `winget install BrechtSanders.WinLibs.POSIX.UCRT` |
| [Claude Code](https://docs.claude.com/claude-code) instalado e logado | `curl -fsSL https://claude.ai/install.sh \| bash` | igual ao Linux | PowerShell: `irm https://claude.ai/install.ps1 \| iex` |
| Git for Windows (o Claude Code usa o Git Bash) | — | — | `winget install Git.Git` |

O Claude Code usa a cota do seu plano, sem API key. Opcional: chave da API do Gemini, usada só se o
Claude falhar. Navegador: Firefox ou Chrome.

Não precisa instalar nada disso antes: o script de início verifica tudo e oferece instalar o que faltar.

## Instalação

### Backend no Linux e no macOS

```bash
git clone https://github.com/fezarosa-dev/moodleChat.git
cd moodleChat
cp bot_moodle/.env.example bot_moodle/.env   # opcional: API_KEY do Gemini (reserva)
./start.sh
```

Se faltar algo, o `start.sh` pergunta *Instalar agora? [S/n]* (usa `dnf`, `apt` ou `pacman`, pedindo a
senha do `sudo`) e, depois de instalar, verifica tudo de novo sozinho.

Em sistema imutável (ex.: Fedora Silverblue) não dá para instalar o `gcc` no sistema: crie uma distrobox,
entre nela (`distrobox enter <box>`) e rode o `start.sh` lá dentro.

No macOS o `start.sh` instala pelo Homebrew (Python) e pelo `xcode-select --install` (gcc). O Receptor
AirPlay ocupa a porta 5000, que a extensão usa: desligue-o em *Ajustes do Sistema → Geral → AirDrop e
Handoff*.

### Backend no Windows

1. Baixe o projeto (`git clone https://github.com/fezarosa-dev/moodleChat.git` ou *Code → Download ZIP*
   no GitHub e extraia).
2. Opcional: copie `bot_moodle\.env.example` para `bot_moodle\.env` e coloque as chaves das IAs que
   for usar (`API_KEY` do Gemini, `ANTHROPIC_API_KEY` da Claude API).
3. Dê dois cliques no `start.bat` (ou rode `start.bat` no terminal).

Se faltar algo, o `start.bat` pergunta *Instalar agora? [S/n]* e instala pelo `winget`. O Claude Code
(se estiver na linha de IAs) se instala com `irm https://claude.ai/install.ps1 | iex` no PowerShell e
precisa do Git for Windows (`winget install Git.Git`). Depois de instalar, **feche o terminal, abra um novo e rode o
`start.bat` de novo** — o Windows só atualiza o PATH em terminais novos. Na primeira vez, rode `claude`
uma vez para fazer login.

> O suporte ao Windows e ao macOS é novo e ainda não foi testado numa máquina real. Se algo falhar, abra uma issue
> com a saída do `start.bat`.

### O que o script de início faz

1. Verifica Python 3.11+, `gcc` (compila e roda um programa de teste; todas as IAs o usam para testar o
   código antes de responder) e a `.venv` com as dependências (cria e instala sozinho).
2. Mostra o **menu de preferências** com as escolhas salvas: **Enter** usa essas, **c** muda
   (ou rode `./start.sh --config` / `start.bat --config` para ir direto). Dá para escolher:
   - a **linha de IAs**, na ordem: Claude Code (CLI, usa o plano logado), Claude API (`ANTHROPIC_API_KEY`)
     e Gemini (`API_KEY`). A primeira responde; se ela falhar (erro, cota, fora do ar), a próxima tenta.
     Todas são tentadas de novo a cada mensagem, mesmo as que falharam antes;
   - o modelo e o effort de cada uma (no Gemini, o modelo inicial: se ele falhar, desce a lista);
   - onde o bot funciona: Moodle, Instagram ou os dois;
   - como falar com o Moodle: pela API (chave `MOODLE_TOKEN`, sem extensão) ou pela extensão;
   - o reinício automático (abaixo).
   As escolhas ficam no `.env` como `BOT_*`.
3. Manda uma mensagem de teste para **cada IA da linha** (gasta um pouco da cota). As que falharem viram
   aviso e continuam na linha; se nenhuma responder, não sobe.
4. Com Instagram escolhido, faz o login e acha a conta da DM; com Moodle pela API, testa a chave; com
   Moodle pela extensão, confere se a porta está livre.

Se estiver tudo certo, sobe o bot. Se não, mostra o que falta e como resolver.

**Reinício automático:** com ele ligado, um vigia sobe o bot e confere a cada 30 s se ele responde. Se o
bot cair ou travar (servidor sem resposta por 2 min, ou Instagram/Moodle sem ler mensagens por 15 min), o vigia o
reinicia com as mesmas preferências. Se reiniciar 5 vezes em 10 min, desiste e mostra o erro (para não
ficar logando no Instagram em loop). **Ctrl+C para os dois.**

**Testes de código:** o Claude Code compila e testa sozinho. As APIs (Claude API e Gemini) recebem uma
ferramenta que compila com `-Wall -Wextra` + sanitizers e roda com as entradas que a IA escolher (até 8
rodadas de testar e corrigir). Se o código ainda falhar nos testes, a resposta sai com um aviso.

Variáveis do `.env` (todas opcionais):

| Variável | Padrão | Uso |
|----------|--------|-----|
| `API_KEY` | — | Chave do Gemini |
| `ANTHROPIC_API_KEY` | — | Chave da Claude API (ou `ant auth login`) |
| `BOT_*` | — | Preferências do menu (melhor mudar pelo `--config`) |
| `DB_FILE` | `moodle_history.duckdb` | Arquivo do banco |
| `PORT` | `5000` | Porta do servidor (a extensão espera 5000) |
| `MOODLE_URL` / `MOODLE_TOKEN` | — | Moodle pela API: endereço do site e a chave do app (ver abaixo) |
| `IG_USERNAME` / `IG_PASSWORD` | — | Conta do Instagram que vai responder (ver abaixo) |
| `IG_SESSIONID` | — | Cookie `sessionid` do navegador, usado no lugar da senha (ver abaixo) |
| `IG_TOTP_SEED` | — | Chave do app autenticador, se a conta tem 2FA: o bot gera o código no login com senha |
| `IG_THREAD` | — | Username da DM que o bot escuta (pode ser a própria conta: conversa consigo mesmo) |

### Moodle pela API (sem extensão)

O bot lê e envia mensagens pela API oficial do Moodle (os web services do app Moodle). Ele olha as suas 20
conversas mais recentes a cada ~5 s e só responde aos comandos `!` que **você** escreveu, na mesma conversa
(a conversa consigo mesmo, em *Mensagens pessoais*, funciona). O que já estava nas conversas ao subir é ignorado.

**Pegar a chave** (o login da UNIFEI é pelo gov.br, então não dá para usar senha): logado no Moodle,
abra uma aba nova, aperte **F12** → **Rede** e marque *Preservar registro*. Acesse

```
https://moodle.unifei.edu.br/admin/tool/mobile/launch.php?service=moodle_mobile_app&passport=12345&urlscheme=moodlemobile
```

cancele o pedido para abrir um app externo, clique na linha `launch.php` e copie o cabeçalho de resposta
`location` (começa com `moodlemobile://token=`). No `.env`:

```
MOODLE_URL=https://moodle.unifei.edu.br
MOODLE_TOKEN=moodlemobile://token=…   # pode colar assim mesmo; o bot extrai a chave
```

- A chave dá acesso à sua conta como o app: trate-a como a senha. Para revogar: *Preferências → Chaves de
  segurança* no Moodle. Ela vence depois de um tempo; o start avisa e mostra como pegar outra.
- **Limitação:** código com `<...>` digitado direto no site do Moodle (ex.: `#include <stdio.h>`) chega
  cortado, porque o próprio site trata como HTML (a extensão evitava isso escapando antes de enviar). O bot
  detecta e pede para reenviar com `&lt;` / `&gt;` em vez de mandar o código quebrado para a IA. As respostas
  do bot saem intactas.

### Instagram (opcional)

Com `IG_USERNAME`, `IG_PASSWORD` e `IG_THREAD` no `.env`, o backend também escuta a DM com
`IG_THREAD` (a cada ~4–6 s) e responde pela sua conta, com os mesmos comandos e o mesmo histórico do
Moodle (uma fila processa uma mensagem por vez). Usa o [instagrapi](https://github.com/subzeroid/instagrapi).

- A sessão fica em `bot_moodle/ig_session.json` para não logar com senha a cada início — trate-o como a senha.
- Respostas longas são quebradas em partes de até 900 bytes (o Instagram aceita 1000 bytes UTF-8 por mensagem).
- Ao subir, o que já está na DM é ignorado: só responde comandos enviados com o bot rodando.
- Se o login com senha falhar (`ClientNeedsUpgradeError`), use o cookie do navegador: abra uma janela anônima,
  entre no instagram.com só com a conta do bot, copie o cookie `sessionid` (F12 → Aplicativo/Armazenamento →
  Cookies) para `IG_SESSIONID` e feche a janela **sem sair** (sair invalida o cookie). O bot confere se a
  sessão é mesmo da conta `IG_USERNAME` e não sobe o Instagram se for de outra.
- Se o Instagram pedir checkpoint/2FA, o bot avisa e desliga só a parte do Instagram: confirme no app e reinicie.
- É a API privada do app, contra os termos do Instagram: há risco de bloqueio da conta. Se o login parar de
  funcionar, atualize o `instagrapi`.

### Extensão

- **Firefox:** `about:debugging` → *Este Firefox* → *Carregar extensão temporária* → escolha o `manifest.json`
  (igual ao `manifest.firefox.json`).
- **Chrome:** copie `manifest.chrome.json` por cima de `manifest.json`, abra `chrome://extensions`,
  ative o *Modo do desenvolvedor* → *Carregar sem compactação* → escolha a pasta do projeto.

Abra o chat do Moodle com o backend rodando e mande `!help`.

## Comandos no chat

| Comando | Descrição |
|---------|-----------|
| `!chat <pergunta>` | Pergunta para a IA |
| `!fix <código>` | Pede correção de bug para a IA |
| `!chata <parte>` | Guarda uma parte de uma pergunta grande, sem chamar a IA |
| `!chatsend [texto]` | Junta as partes guardadas e envia como uma pergunta |
| `!chclear` | Limpa a conversa |
| `!help` | Mostra todos os comandos |

**Conversa contínua:** `!chat` e `!fix` compartilham o mesmo histórico. A IA recebe automaticamente
as últimas 20 interações desde o último `!chclear` — não é preciso indicar IDs nem repetir o código.

**Código testado:** quando a resposta do Claude tem código C, ele compila e roda o código numa pasta
temporária antes de responder. Respostas vindas do Gemini avisam que o código não foi testado.
Para rodar o **seu** código, peça à IA: `!chat roda esse código com a entrada 5 ...`.

**Código com `<` e `>`:** o Moodle trata as mensagens como HTML, então `#include <stdio.h>` ou
`if (a<b && c>d)` sumiriam. A extensão escapa o texto (`&lt;`, `&gt;`, `&amp;`) ao enviar — tanto o que
você digita quanto as respostas do bot — e o código aparece e chega ao bot exatamente como foi escrito.

### Execução direta (`!run`) — desativada

`!run <código C>`, `!r <valor>` e `!kill` compilavam e executavam o código direto, com entrada interativa.
Estão desativados por enquanto (respondem avisando); o código continua no projeto. Para reativar, mude
`RUN_ATIVO = True` em `bot_moodle/bot_moodle/routes/chat.py`.

## Estrutura do projeto

```
moodleChat/
├── manifest*.json      # Manifests da extensão (Firefox / Chrome)
├── content.js          # Lê o chat do Moodle e escreve as respostas
├── chatUsage.js        # Extração das mensagens e chamada ao backend
├── background.js
├── start.sh / .bat     # Verifica o ambiente e sobe o backend (Linux e macOS / Windows)
└── bot_moodle/
    ├── tests/          # Testes (pytest)
    └── bot_moodle/
        ├── app.py          # Entry point / Flask factory
        ├── moodle_api.py   # Moodle pela API oficial (sem extensão)
        ├── instagram.py    # DM do Instagram
        ├── preferencias.py # Menu do start (BOT_* no .env)
        ├── checagens.py    # Testes do start (IAs, Moodle, Instagram, porta)
        ├── vigia.py        # Reinicia o bot se cair ou travar
        ├── core/
        │   ├── runner.py   # Compilação e execução de C (timer de silêncio)
        │   ├── ai.py       # Claude via `claude -p`, Gemini como reserva
        │   └── headers.py  # Inferência automática de #include
        ├── db/
        │   └── database.py # DuckDB: histórico, runs e buffer do !chata
        └── routes/
            └── chat.py     # Handlers de todos os comandos
```

## Desenvolvimento

Instale os extras de desenvolvimento e rode, dentro de `bot_moodle/`:

```bash
.venv/bin/pip install -e ".[dev]"      # Windows: .venv\Scripts\pip install -e ".[dev]"
.venv/bin/pylint bot_moodle            # o CI exige nota >= 8
.venv/bin/pytest                       # os testes do runner são pulados sem gcc
```

## Segurança

Os testes que a IA faz (e o `!run`, se reativado) executam código arbitrário na sua máquina, com o seu usuário.
Use só em chats em que você confia.
