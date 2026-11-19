# Guia de desenvolvimento

Como mexer no bot com segurança: o ambiente, os testes (TDD), o padrão de código e o CI.
Como as partes se encaixam está em [arquitetura.md](arquitetura.md).

## Ambiente

Na raiz do projeto:

```bash
python3 -m venv .venv                  # o ./start.sh já cria
.venv/bin/pip install -e ".[dev]"      # o bot em modo editável + pytest e pylint
```

No Windows, troque `.venv/bin/` por `.venv\Scripts\`. Para os testes da extensão, Node 20 ou mais novo.

## Rodando os testes

```bash
.venv/bin/pytest                         # tudo (~20 s)
.venv/bin/pytest tests/ia                # só uma parte: a pasta tests/ espelha bot_moodle/
.venv/bin/pytest tests/test_comandos.py  # só um arquivo
.venv/bin/pytest -k chatsend             # só os testes com "chatsend" no nome
node --test "extensao/tests/*.test.js"   # a extensão
```

Para mudanças pequenas, rode só os testes da parte que você mexeu (`tests/<pasta>` da mesma pasta de
`bot_moodle/`); o CI roda tudo nos três sistemas antes do merge.

Os testes que compilam C (`tests/ia/test_testador.py`, `tests/execucao/test_runner.py`) são pulados se não
houver `gcc`.

### O que os testes garantem por conta própria (`tests/conftest.py`)

- **Pasta isolada:** cada teste roda numa pasta temporária, então nenhum teste lê ou escreve o `.env`, o
  banco ou as sessões de verdade (os caminhos do bot são relativos à pasta atual).
- **Ambiente limpo:** as variáveis do bot (`BOT_*`, `IG_*`, `MOODLE_*`, chaves) são apagadas antes de cada
  teste: o resultado não depende do `.env` de quem roda, e no GitHub nem existe `.env`.
- **IA falsa:** a fixture `ia` troca a IA de verdade por uma que responde `resp:<pergunta>` e guarda cada
  chamada — nada de rede nem de cota.
- **Bot de teste:** a fixture `enviar` manda mensagens para a rota como o Moodle mandaria e devolve o JSON.
- **Runner limpo:** o `!run` em memória é zerado depois de cada teste.

Moodle, Instagram, Claude e Gemini também são simulados nos testes deles (`urlopen`, `Client` do
instagrapi, SDK da Anthropic e cliente do Gemini falsos).

## TDD: como adicionar ou mudar um comportamento

1. **Escreva o teste primeiro**, descrevendo o comportamento visto de fora, com um nome que é uma frase:
   `test_chatsend_junta_as_partes_e_o_texto_final`. O nome faz o papel da docstring.
2. **Rode e veja falhar** (vermelho): confirma que o teste testa algo de verdade.
3. **Escreva o mínimo de código** para passar (verde).
4. **Refatore** com os testes verdes: nomes melhores, funções menores, sem repetição.
5. **Rode o pylint** e os testes da parte que mudou; o CI roda o resto.

Para refatorar código que já existe sem teste, faça o contrário do passo 2: escreva testes que **passam** no
código atual (eles registram o comportamento de hoje) e só então refatore, mantendo-os verdes.

### Exemplo: um comando novo `!ping`

O teste, em `tests/test_comandos.py`:

```python
def test_ping_responde_pong(enviar):
    assert enviar("!ping")["resposta"] == "pong"
```

O código, em `bot_moodle/comandos.py`: uma função que recebe a `Mensagem` e devolve o texto, e uma linha na
tabela.

```python
def _ping(_msg: Mensagem) -> str:
    return "pong"


COMANDOS = {..., "ping": _ping}
```

E uma linha no `ajuda()`, para o `!help` mostrar o comando novo (com um teste no
`test_help_lista_os_comandos`).

## Padrão de código

- **Zen of Python e Clean Code:** funções pequenas com um nome que diz o que fazem; *flat is better than
  nested*.
- **Sem `if` encadeado:** retorno antecipado (*guard clause*) para os casos especiais e tabela
  (`dict` de funções) no lugar de `if/elif` longos — veja `COMANDOS` em `comandos.py` e `PROVEDORES` em
  `ia/linha.py`.
- **Um lugar para cada coisa:** caminhos de arquivo só em `caminhos.py`; escolhas do menu só via
  `preferencias.pref`; nada de `load_dotenv()` ao importar um módulo (só nos `main`).
- **Nomes em português**, como o resto do projeto; termos técnicos e da API ficam como são.
- **Comentários dizem o porquê**, não o quê (ex.: por que `_IONBF` e não `_IOLBF`).
- **pylint** sem avisos: o CI exige nota mínima 9.5 no código e nos testes.

## O CI (GitHub Actions)

O arquivo é `.github/workflows/ci.yml`. A cada envio para qualquer branch e a cada PR:

| Job | O que faz |
|-----|-----------|
| **Testes (ubuntu, macos, windows)** | instala o bot e roda o `pytest` nos três sistemas; um sistema falhando não esconde os outros |
| **Pylint, extensão e scripts** | pylint no código e nos testes (nota mínima 9.5), `node --test` na extensão e `bash -n start.sh` |

O fluxo de trabalho: commits na `dev`, PR da `dev` para a `main`, merge só com o CI verde.

## Estrutura

```
bot_moodle/          o código (veja arquitetura.md)
tests/               os testes, na mesma estrutura de bot_moodle/
  conftest.py        isolamento, IA falsa, bot de teste
extensao/            a extensão do navegador
  tests/             os testes do texto.js (Node)
docs/                este guia e a arquitetura
```
