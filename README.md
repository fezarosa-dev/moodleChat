# Moodle Chat Bot — Assistente Acadêmico de Programação

Extensão de navegador + backend local que transformam o chat do Moodle num assistente de programação:
compila e executa código C pelo próprio chat e conversa com uma IA (Claude Code logado na máquina,
Gemini como reserva) para tirar dúvidas e corrigir código.

## Como funciona

1. A extensão (`content.js` / `chatUsage.js`) lê o chat do Moodle a cada 2 s e envia cada mensagem
   nova para o backend em `http://localhost:5000/check_and_save`.
2. O backend (Flask + DuckDB) identifica comandos (`!chat`, `!fix`…), executa e devolve a resposta.
3. A extensão escreve a resposta no chat, quebrando em várias mensagens quando passa do limite do Moodle.

Mensagens que não começam com `!` são só registradas, sem resposta.

## Requisitos

| | Linux | Windows |
|---|---|---|
| Python 3.11+ | pacote `python3` (+ `python3-venv` no Debian/Ubuntu) | `winget install Python.Python.3.13` |
| GCC (para a IA compilar e testar o código) | pacote `gcc` | MinGW: `winget install BrechtSanders.WinLibs.POSIX.UCRT` |
| [Claude Code](https://docs.claude.com/claude-code) instalado e logado | `curl -fsSL https://claude.ai/install.sh \| bash` | PowerShell: `irm https://claude.ai/install.ps1 \| iex` |
| Git for Windows (o Claude Code usa o Git Bash) | — | `winget install Git.Git` |

O Claude Code usa a cota do seu plano, sem API key. Opcional: chave da API do Gemini, usada só se o
Claude falhar. Navegador: Firefox ou Chrome.

Não precisa instalar nada disso antes: o script de início verifica tudo e oferece instalar o que faltar.

## Instalação

### Backend no Linux

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

### Backend no Windows

1. Baixe o projeto (`git clone https://github.com/fezarosa-dev/moodleChat.git` ou *Code → Download ZIP*
   no GitHub e extraia).
2. Opcional: copie `bot_moodle\.env.example` para `bot_moodle\.env` e coloque a `API_KEY` do Gemini.
3. Dê dois cliques no `start.bat` (ou rode `start.bat` no terminal).

Se faltar algo, o `start.bat` pergunta *Instalar agora? [S/n]* e instala pelo `winget` (o Claude Code
pelo instalador oficial no PowerShell). Depois de instalar, **feche o terminal, abra um novo e rode o
`start.bat` de novo** — o Windows só atualiza o PATH em terminais novos. Na primeira vez, rode `claude`
uma vez para fazer login.

> O suporte ao Windows é novo e ainda não foi testado numa máquina real. Se algo falhar, abra uma issue
> com a saída do `start.bat`.

### O que o script de início verifica

- Python 3.11+ e `gcc` (compila e roda um programa de teste);
- Claude Code instalado **e logado** (manda uma pergunta mínima — gasta um pouco da cota);
- no Windows, também o Git for Windows;
- `.venv` com as dependências Python — se não existir, é criada e instalada automaticamente;
- porta livre;
- `.env` e `API_KEY` (só avisa: são opcionais).

Se estiver tudo certo, sobe o bot. Se não, mostra o que falta e como instalar.

Variáveis do `.env` (todas opcionais):

| Variável | Padrão | Uso |
|----------|--------|-----|
| `API_KEY` | — | Chave do Gemini (reserva) |
| `DB_FILE` | `moodle_history.duckdb` | Arquivo do banco |
| `PORT` | `5000` | Porta do servidor (a extensão espera 5000) |

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
├── start.sh / .bat     # Verifica o ambiente e sobe o backend (Linux / Windows)
└── bot_moodle/
    ├── tests/          # Testes (pytest)
    └── bot_moodle/
        ├── app.py          # Entry point / Flask factory
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
