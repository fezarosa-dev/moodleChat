# Bot Moodle — Assistente Acadêmico de Programação

Bot integrado ao Moodle que permite compilar e executar código C diretamente
pelo chat, com suporte a IA (Gemini) para tirar dúvidas e corrigir código.

## Requisitos

- Python 3.11+
- GCC instalado (`sudo apt install gcc` no Linux)

## Instalação

```bash
# 1. Clone o repositório
git clone [https://github.com/seu-usuario/bot-moodle.git](https://github.com/fezarosa-dev/moodleChat.git)
cd bot-moodle

# 2. Crie e ative a venv
python -m venv .venv
source .venv/bin/activate      # Linux/macOS
# ou
.venv\Scripts\activate         # Windows

# 3. Instale as dependências
pip install -e ".[dev]"

# 4. Configure o ambiente
cp .env.example .env
# Edite .env e coloque sua API_KEY do Gemini

# 5. Inicie o servidor
bot-moodle
# ou
python -m bot_moodle.app
```

## Estrutura do projeto

```
bot_moodle/
├── app.py          # Entry point / Flask factory
├── core/
│   ├── runner.py   # Compilação e execução de C (timer de silêncio)
│   ├── ai.py       # Integração Gemini com fallback de modelos
│   └── headers.py  # Inferência automática de #include
├── db/
│   └── database.py # Conexão DuckDB e helpers de persistência
└── routes/
    └── chat.py     # Handlers de todos os comandos (!run, !chat, !fix…)
```

## Comandos disponíveis no chat

| Comando | Descrição |
|---------|-----------|
| `!run <código C>` | Compila e executa o código |
| `!r <valor>` | Envia input para o programa em execução |
| `!kill` | Encerra o programa e entrega a saída |
| `!chat <pergunta>` | Pergunta para a IA |
| `!fix <código>` | Pede correção de bug para a IA |
| `!chat+<id> <pergunta>` | Inclui o run de `<id>` como contexto |
| `!fix+<id> <código>` | Fix com contexto do run de `<id>` |
| `!chatN <pergunta>` | Inclui as últimas N interações como contexto |
| `!chatid<regras> <pergunta>` | Contexto cirúrgico por IDs |
| `!help` | Exibe todos os comandos |

## Desenvolvimento

```bash
# Lint
pylint bot_moodle

# Testes
pytest
```
