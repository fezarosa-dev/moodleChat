# Arquitetura

Como o bot funciona por dentro: as partes, o caminho de uma mensagem e as decisões por trás de cada uma.
Para usar o bot, veja o [README](../README.md); para mexer no código, o [guia de desenvolvimento](desenvolvimento.md).

## Visão geral

```
                ┌─────────────── start.sh / start.bat ───────────────┐
                │ ambiente → menu (inicio/preferencias) → checagens  │
                │ (inicio/checagens) → bot-moodle (app.main)         │
                └───────────────────────────┬────────────────────────┘
                                            │
                          vigia (inicio/vigia): processo pai que
                          reinicia o bot se ele cair ou travar
                                            │
   ┌────────────────────────────────────────┼─────────────────────────────────────┐
   │ app.py: sobe cada plataforma com a sua sequência de jeitos de conectar       │
   │                                                                              │
   │  Moodle pela API           Servidor da extensão         Instagram            │
   │  (plataformas/moodle)      (plataformas/extensao)       (plataformas/        │
   │  thread que lê as          thread na porta 5000;        instagram) thread    │
   │  conversas a cada 5 s      a extensão do navegador      que lê a DM          │
   │                            manda as mensagens           a cada 4–6 s         │
   │            └──────────────────────┬──────────────────────────┘               │
   │                                   ▼                                          │
   │               POST /check_and_save  (comandos.py)                            │
   │      registra a mensagem (db.py) → escolhe o comando na tabela → responde    │
   │                                   │                                          │
   │                                   ▼                                          │
   │                 ia/linha.py: Claude Code → Claude API → Gemini               │
   │                 (na ordem do menu; cada uma testa o código C)                │
   └──────────────────────────────────────────────────────────────────────────────┘
```

Todas as plataformas falam com o bot pela **mesma rota** (`/check_and_save`): é isso que faz os comandos e o
histórico serem iguais no Moodle e no Instagram. A extensão chama a rota pela rede (porta 5000); a API do
Moodle e o Instagram chamam a mesma rota por dentro, com o cliente de testes do Flask (`app.test_client()`),
sem abrir porta.

## O caminho de uma mensagem

Exemplo: você manda `!chat o que é ponteiro?` na conversa consigo mesmo, no Moodle pela API.

1. **Leitura** (`plataformas/moodle.py`, `_ciclo`): a cada 5 s a thread pede as 20 conversas mais
   recentes. Só busca as mensagens de uma conversa se a última mensagem dela mudou desde a leitura
   anterior (`Leitura.visto`). Das mensagens novas, só segue com as **suas**, criadas depois de o bot subir
   e que não são respostas do próprio bot (`Leitura.e_comando_novo`).
2. **Texto** (`texto`): a API devolve HTML (`<p>…<br>…</p>`, `&lt;`). O bot converte de volta para o
   texto digitado, com quebras de linha e indentação. Se o site apagou trechos entre `<` e `>` (código
   digitado direto no site), `comido` percebe e o bot avisa em vez de seguir.
3. **Rota** (`comandos.py`, `check_and_save`): a mensagem entra na fila (um `Lock`: Moodle e Instagram
   chegam em threads diferentes e o histórico não pode intercalar), é gravada no banco pelo id e, se o id
   já existia, a rota responde `duplicate` (é assim que nada é respondido duas vezes, nem trocando de modo:
   a API e a extensão usam o mesmo id da mensagem do Moodle).
4. **Comando** (`Mensagem.ler` e a tabela `COMANDOS`): `!chat o que…` vira comando `chat` com argumento
   `o que…`. A tabela leva ao handler `_chat`, que chama `_perguntar`.
5. **IA** (`ia/linha.py`, `pedir_a_ia`): monta o prompt (papel, regras de formatação, a conversa desde o
   último `!chclear` e a pergunta) e tenta as IAs na ordem do menu até uma responder. Cada uma testa o
   código C que escrever (veja [As IAs](#as-ias)).
6. **Histórico** (`db.py`): a resposta é gravada ligada à pergunta; na próxima mensagem ela entra no
   contexto.
7. **Resposta** (`moodle._enviar`): a resposta é quebrada em partes de até 3000 bytes, numeradas
   `(1/2)`, e enviada em texto puro (o Moodle guarda `<`, `&&` e a indentação como estão). Os ids das
   partes enviadas entram em `Leitura.pular`, para o bot não ler a própria resposta como comando.

## Os módulos

### `app.py` — o ponto de entrada

- `Escolhas`: o que sobe, lido das preferências (`BOT_PLATAFORMAS`, `BOT_MOODLE_MODOS`, `BOT_VIGIA`).
- `create_app`: o Flask com a rota dos comandos, o banco e o cliente do Gemini.
- `Plataforma`: uma plataforma e a sua **sequência de jeitos de conectar** (a reserva). `subir` tenta os
  jeitos em ordem até um dar certo (`INICIAR_MOODLE["api"]` devolve `None` sem chave; a extensão devolve
  `None` com a porta ocupada).
- `_manter`: o laço principal. A cada segundo confere se cada plataforma está de pé; se o leitor atual
  parou (ex.: a chave do Moodle venceu), sobe o próximo jeito da sequência. Quando nenhuma plataforma
  tem mais jeito para tentar, sai com o código `NAO_REINICIAR` (reiniciar só repetiria o erro).

### `comandos.py` — os comandos do chat

- `Mensagem`: a mensagem separada em comando e argumento (`!fix\nint main` → `fix`, `int main`).
- `COMANDOS`: a tabela `nome → função`. Cada função recebe a `Mensagem` e devolve **só o texto** da
  resposta; quem monta o JSON é `_executar`. Adicionar um comando é adicionar uma linha na tabela.
- `COMANDOS_RUN`: `!run`, `!r` e `!kill`, desligados por `RUN_ATIVO = False`. Ficam numa tabela à parte
  porque cuidam sozinhos da saída pendente do programa (o `!kill` não pode consumi-la antes de rodar).
- Erros inesperados viram uma resposta `❌ Erro no servidor: …` no chat, em vez de sumirem.

### `db.py` — o banco

DuckDB em `dados/moodle_history.duckdb`. Tabelas:

| Tabela | Guarda |
|--------|--------|
| `mensagens_usuario` | toda mensagem recebida (o id é o registro de "já vi esta") |
| `respostas_ia` | a resposta de cada `!chat`/`!fix` |
| `runs` | os `!run` (código, entradas, saída), que entram no contexto da IA |
| `buffer_chat` | as partes guardadas pelo `!chata` até o `!chatsend` |

O `!chclear` apaga o texto da conversa mas **mantém os ids**: senão, as mensagens antigas ainda visíveis no
Moodle seriam respondidas de novo.

### `ia/` — as IAs

- `linha.py`: monta o prompt e percorre a linha de reserva (`PROVEDORES`, na ordem de `BOT_IAS`). Uma IA
  que falha (erro, cota, recusa, resposta vazia) passa a vez; na mensagem seguinte todas são tentadas de
  novo. No fim da resposta, `aviso` diz se o código não passou nos testes ou não foi testado.
- `claude_cli.py`: roda `claude -p` numa pasta temporária, com só as ferramentas de escrever arquivos,
  `gcc`, o programa compilado e `printf`, e sem as configurações pessoais do Claude Code. Ele testa sozinho.
- `claude_api.py`: a Messages API com a ferramenta `testar_c`, num laço de até 8 testes: a cada pedido da
  IA, o bot compila e roda e devolve o resultado.
- `gemini.py`: o Gemini com a mesma ferramenta (chamada automática de funções). Se o modelo escolhido
  falhar, desce a lista `MODELOS_GEMINI`.
- `testador.py`: o `testar_c`. Compila com `gcc -Wall -Wextra` e AddressSanitizer/UBSan (sem eles se não
  linkarem, como no MinGW do Windows), roda com cada entrada (10 s de limite) e diz se passou: sem avisos,
  código de saída 0 e nenhum erro dos sanitizers.

### `plataformas/` — onde o bot conversa

- `moodle.py`: a API oficial (veja [O caminho de uma mensagem](#o-caminho-de-uma-mensagem)). `ws` chama as
  funções da API (com os certificados do `certifi`, porque o Python do python.org no macOS não acha os do
  sistema); `ChaveInvalida` separa "a chave venceu" (não adianta tentar de novo) de "a rede caiu" (tenta
  de novo a cada 30 s).
- `extensao.py`: o servidor da porta 5000, numa thread, para a extensão do navegador. Confere a porta antes
  de subir (com a porta ocupada, o servidor do werkzeug encerraria o programa inteiro).
- `instagram.py`: o login segue `BOT_IG_LOGIN` (`entrar` tenta cada jeito e devolve qual funcionou e quais
  falharam). Uma **trava** recusa qualquer sessão que não seja da conta `IG_USERNAME`. A leitura da DM
  ignora o que já existia ao subir e as respostas do próprio bot. A sessão fica em `dados/ig_session.json`
  para não repetir o login com senha (login repetido é sinal de risco para o Instagram).

### `inicio/` — o start

- `preferencias.py`: o menu. Na primeira vez (sem `BOT_CONFIGURADO=1`) abre sozinho. Pergunta a linha de
  IAs, as plataformas, os jeitos de conectar (com reserva) e, por fim, só as chaves que essas escolhas
  precisam (`_chaves_necessarias`); os segredos são pedidos com `getpass`. `salvar` troca as linhas do
  `.env` e põe aspas quando o valor tem espaço ou `#`.
- `checagens.py`: imprime uma linha por item (`OK`, `AVISO`, `PULA`, `ERRO`, `DICA`); o `start.sh`/
  `start.bat` desenha cada uma e trata `ERRO` como impeditivo. Testa cada IA da linha com uma mensagem
  curta, cada jeito do Moodle na ordem e o login do Instagram.
- `vigia.py`: um processo pai que roda o bot como filho e o reinicia se ele cair, se o servidor da extensão
  parar de responder em `/health` (depois de ter respondido uma vez: com a reserva, ele pode nem subir) ou
  se o Moodle/Instagram parar de tocar o seu arquivo de vida em `dados/`. Ctrl+C e erros em que reiniciar
  não resolve param tudo; 5 reinícios em 10 min também.

### `execucao/` — o `!run` (desativado)

- `runner.py`: cada `!run` é uma `Execucao` com o próprio processo, filas e uma thread (o monitor) que
  entrega a saída quando o programa termina ou fica 5 s em silêncio. Cada monitor só mexe na própria
  execução — antes, com um estado global, um `!run` logo depois de um `!kill` era confundido com o
  anterior.
- `headers.py`: reconstrói os `#include` que o chat apaga (`#include <stdio.h>` vira só `#include`),
  olhando as funções que o código usa.

### `caminhos.py`

O único lugar que diz onde ficam os arquivos do usuário: o `.env` na raiz e o resto em `dados/`. Os
caminhos são relativos à pasta atual (o start roda o bot da raiz), o que também deixa os testes rodarem
numa pasta temporária.

## A extensão (`extensao/`)

- `texto.js`: funções puras (sem DOM), testadas no Node: `escaparHtml` (o Moodle trata a mensagem como
  HTML, então `<stdio.h>` sumiria) e `dividirMensagem` (partes numeradas que nunca começam com `!`, sem
  cortar uma entidade `&amp;` no meio).
- `content.js`: lê as mensagens novas do chat aberto a cada 2 s, manda para o bot e escreve a resposta;
  também escapa o que você digita antes de o Moodle enviar.
- `chatUsage.js`: a chamada ao bot (`http://localhost:5000/check_and_save`).

## Decisões

| Decisão | Por quê |
|---------|---------|
| Uma rota para todas as plataformas | Comandos e histórico iguais em todo lugar, num só código |
| Dedup pelo id da mensagem no banco | Reiniciar o bot ou trocar de modo nunca responde duas vezes |
| Reserva por plataforma (`Plataforma`) | Uma chave vencida ou uma porta ocupada não derrubam o Moodle |
| Vigia num processo separado | Um travamento dentro do bot não trava quem o reinicia |
| Arquivos do usuário fora do código (`.env`, `dados/`) | O código pode ser atualizado ou apagado sem perder chaves e histórico |
| Testes com tudo simulado e em pasta temporária | Rodam no CI sem chaves e nunca tocam os dados reais |
