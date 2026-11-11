# Moodle Chat Bot — Assistente Acadêmico de Programação

Extensão de navegador + backend local que transformam o chat do Moodle num assistente de programação:
compila e executa código C pelo próprio chat e conversa com uma IA (Claude Code logado na máquina,
Gemini como reserva) para tirar dúvidas e corrigir código.

## Como funciona

1. A extensão (`content.js` / `chatUsage.js`) lê o chat do Moodle a cada 2 s e envia cada mensagem
   nova para o backend em `http://localhost:5000/check_and_save`.
2. O backend (Flask + DuckDB) identifica comandos (`!chat`, `!run`…), executa e devolve a resposta.
3. A extensão escreve a resposta no chat, quebrando em várias mensagens quando passa do limite do Moodle.

Mensagens que não começam com `!` são só registradas, sem resposta.

## Requisitos

- Python 3.11+
- GCC (para `!run` e para a IA testar o código antes de responder)
- [Claude Code](https://docs.claude.com/claude-code) instalado e logado (`claude`) — usa a cota do seu plano
- Opcional: chave da API do Gemini, usada só se o Claude falhar
- Firefox ou Chrome

## Instalação

### Backend

```bash
git clone https://github.com/fezarosa-dev/moodleChat.git
cd moodleChat
cp bot_moodle/.env.example bot_moodle/.env   # opcional: API_KEY do Gemini (reserva)
./start.sh
```

O `start.sh` verifica o ambiente antes de subir o bot e, se faltar algo, diz o que instalar:

- Python 3.11+ e `gcc` (compila e roda um programa de teste);
- Claude Code instalado **e logado** (manda uma pergunta mínima — gasta um pouco da cota);
- `.venv` com as dependências — se não existir, é criada e instalada automaticamente;
- porta livre;
- `.env` e `API_KEY` (só avisa: são opcionais).

Se o `gcc`/`claude` estiverem numa distrobox (ex.: Fedora Silverblue), entre nela antes
(`distrobox enter <box>`) e rode o `start.sh` lá dentro.

Para desenvolver (pylint/pytest), instale também os extras: `bot_moodle/.venv/bin/pip install -e "bot_moodle[dev]"`.

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
| `!run <código C>` | Compila e executa o código |
| `!r <valor>` | Envia uma entrada para o programa em execução |
| `!kill` | Encerra o programa e entrega toda a saída |
| `!chclear` | Limpa a conversa (perguntas, respostas e runs) |
| `!help` | Mostra todos os comandos |

**Conversa contínua:** `!chat` e `!fix` compartilham o mesmo histórico. A IA recebe automaticamente
as últimas 20 interações (perguntas, respostas e `!run` com código, entradas e saída) desde o último
`!chclear` — não é preciso indicar IDs nem repetir o código.

**Execução:** a saída do `!run` chega depois de 5 s sem novo output, ou na hora com `!kill`.

**Código testado:** quando a resposta do Claude tem código C, ele compila e roda o código numa pasta
temporária antes de responder. Respostas vindas do Gemini avisam que o código não foi testado.

## Estrutura do projeto

```
moodleChat/
├── manifest*.json      # Manifests da extensão (Firefox / Chrome)
├── content.js          # Lê o chat do Moodle e escreve as respostas
├── chatUsage.js        # Extração das mensagens e chamada ao backend
├── background.js
├── start.sh            # Sobe o backend
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

Dentro de `bot_moodle/`:

```bash
pylint bot_moodle   # o CI exige nota >= 8
pytest
```

## Segurança

`!run` (e os testes que a IA faz) executam código arbitrário na sua máquina, com o seu usuário.
Use só em chats em que você confia.
