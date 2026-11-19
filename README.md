# Moodle Chat Bot — Assistente Acadêmico de Programação

Bot que roda no seu computador e transforma o chat do Moodle (e, se quiser, uma DM do Instagram) num
assistente de programação: você manda `!chat` ou `!fix` com a sua dúvida ou o seu código C, uma IA responde
e, antes de responder, **compila e testa** o código que ela escreveu.

- **IAs:** Claude Code (usa o seu plano do Claude, sem API key), Claude API e Gemini, numa linha de reserva
  que você monta: se a primeira falhar, a próxima responde.
- **Moodle:** pela API oficial (a mesma do app do celular, **sem extensão**) e/ou pela extensão de navegador,
  com reserva: se um jeito falhar, o outro assume.
- **Instagram (opcional):** os mesmos comandos por uma DM; login por senha (com 2FA) e/ou cookie, com reserva.
- **Sempre de pé:** um vigia reinicia o bot se ele cair ou travar.
- **Configuração guiada:** na primeira vez, um menu pergunta tudo (IAs, plataformas, jeitos de conectar e
  as chaves) e testa as conexões antes de subir.

## Sumário

1. [Como funciona](#como-funciona)
2. [Requisitos](#requisitos)
3. [Passo a passo do zero](#passo-a-passo-do-zero)
4. [O menu e o script de início](#o-menu-e-o-script-de-início)
5. [Moodle pela API (sem extensão)](#moodle-pela-api-sem-extensão)
6. [As IAs e suas chaves](#as-ias-e-suas-chaves)
7. [Usando os comandos](#usando-os-comandos)
8. [Instagram (opcional)](#instagram-opcional)
9. [Moodle pela extensão](#moodle-pela-extensão)
10. [Variáveis do `.env`](#variáveis-do-env)
11. [Problemas comuns](#problemas-comuns)
12. [Segurança](#segurança)
13. [Estrutura do projeto](#estrutura-do-projeto)
14. [Desenvolvimento](#desenvolvimento)

## Como funciona

1. Você escreve um comando que começa com `!` numa conversa do Moodle (ex.: `!chat o que é ponteiro?`).
2. O bot, rodando no seu computador, percebe a mensagem nova:
   - **pela API:** a cada ~5 s ele olha as suas conversas pela API oficial do Moodle;
   - **pela extensão:** a extensão lê o chat aberto no navegador a cada 2 s e manda para o bot.
3. O bot passa a pergunta para a primeira IA da linha, com o histórico da conversa. Se a resposta tem
   código C, a IA compila e testa antes de responder.
4. A resposta aparece na mesma conversa, quebrada em várias mensagens `(1/2)`, `(2/2)`… se for longa.

Mensagens que não começam com `!` são ignoradas (só ficam registradas). Todo o histórico fica num banco
local (`dados/moodle_history.duckdb`), compartilhado entre Moodle e Instagram. O funcionamento por dentro
está em [docs/arquitetura.md](docs/arquitetura.md).

## Requisitos

| | Linux | macOS | Windows |
|---|---|---|---|
| Python 3.11+ | pacote `python3` (+ `python3-venv` no Debian/Ubuntu) | `brew install python@3.13` | `winget install Python.Python.3.13` |
| GCC (para a IA compilar e testar o código) | pacote `gcc` | `xcode-select --install` (o `gcc` é o clang) | MinGW: `winget install BrechtSanders.WinLibs.POSIX.UCRT` |
| [Claude Code](https://docs.claude.com/claude-code) instalado e logado (se usar) | `curl -fsSL https://claude.ai/install.sh \| bash` | igual ao Linux | PowerShell: `irm https://claude.ai/install.ps1 \| iex` |
| Git for Windows (o Claude Code usa o Git Bash) | — | — | `winget install Git.Git` |

Além disso: uma conta no Moodle e **pelo menos uma IA** (Claude Code logado, uma chave do Gemini ou uma
chave da Claude API — veja [As IAs e suas chaves](#as-ias-e-suas-chaves)).

Não precisa instalar nada disso antes: o script de início verifica tudo e oferece instalar o que faltar.

## Passo a passo do zero

**1. Baixe o projeto.**

```bash
git clone https://github.com/fezarosa-dev/moodleChat.git
cd moodleChat
```

No Windows dá também para usar *Code → Download ZIP* no GitHub e extrair.

**2. Prepare pelo menos uma IA** ([detalhes](#as-ias-e-suas-chaves)): o mais simples é o **Claude Code**
(usa o seu plano do Claude): instale (tabela acima) e rode `claude` uma vez no terminal para fazer login.
Se for usar o Gemini ou a Claude API, tenha a chave em mãos: o menu vai pedir.

**3. Se for usar o Moodle pela API, pegue a chave do Moodle** — siga [Pegar a chave](#pegar-a-chave).
Leva 2 minutos. O menu vai pedir para colar.

**4. Rode o script de início:**

```bash
./start.sh                  # Linux e macOS
start.bat                   # Windows (ou dois cliques no arquivo)
```

Na primeira vez ele cria o ambiente Python, instala as dependências e **abre o menu de configuração
sozinho**: você escolhe as IAs, onde o bot funciona (Moodle, Instagram ou os dois), como ele conecta em cada
um (com reserva, se quiser) e cola as chaves pedidas. Tudo fica salvo no `.env` (na raiz do projeto). Depois
ele **testa cada conexão** e sobe o bot.

**5. Teste:** no Moodle, abra as mensagens e mande `!help` para você mesmo (veja
[onde mandar os comandos](#onde-mandar-os-comandos)). Em alguns segundos chega o guia de comandos.

Para parar o bot: **Ctrl+C** no terminal. Para mudar as escolhas depois: `./start.sh --config`.

### Notas por sistema

- **Linux:** se faltar algo, o `start.sh` pergunta *Instalar agora? [S/n]* (usa `dnf`, `apt` ou `pacman`,
  pedindo a senha do `sudo`) e verifica tudo de novo. Em sistema imutável (ex.: Fedora Silverblue), crie uma
  distrobox, entre nela (`distrobox enter <box>`) e rode o `start.sh` lá dentro.
- **macOS:** o `start.sh` instala pelo Homebrew (Python) e pelo `xcode-select --install` (gcc). Só para o
  modo extensão: o Receptor AirPlay ocupa a porta 5000; desligue-o em *Ajustes do Sistema → Geral →
  AirDrop e Handoff*.
- **Windows:** o `start.bat` instala o que faltar pelo `winget`. Depois de instalar algo, **feche o terminal,
  abra um novo e rode o `start.bat` de novo** — o Windows só atualiza o PATH em terminais novos. O Claude
  Code precisa do Git for Windows.

Os testes automáticos rodam no Linux, no macOS e no Windows a cada mudança (veja
[Desenvolvimento](#desenvolvimento)); o uso de ponta a ponta foi conferido no Linux.

### Atualizando de uma versão antiga

Até a v1.x o código ficava em `bot_moodle/bot_moodle/`, os seus arquivos (`.env`, banco, sessões do
Instagram) em `bot_moodle/` e a extensão solta na raiz. Depois de atualizar (`git pull`):

- rode o start normalmente: ele **move sozinho** o `.env` para a raiz e o banco e as sessões para `dados/`,
  sem sobrescrever nada, e recria a `.venv`. Como as opções de conexão são novas, o menu abre uma vez para
  você conferir;
- se usa a extensão, **carregue-a de novo** a partir da pasta `extensao/` (veja
  [Moodle pela extensão](#moodle-pela-extensão)).

## O menu e o script de início

O `start.sh` / `start.bat` faz, em ordem:

1. Verifica Python 3.11+, `gcc` (compila e roda um programa de teste) e a `.venv` com as dependências
   (cria e instala sozinho). Se achar a estrutura antiga, migra os seus arquivos.
2. Mostra o **menu de preferências**. Na **primeira vez** (sem `BOT_CONFIGURADO=1` no `.env`) ele abre
   sozinho; depois, **Enter** usa as escolhas salvas e **c** muda (ou rode `./start.sh --config` /
   `start.bat --config` para ir direto). O menu pergunta:
   - a **linha de IAs**, digitando os números na ordem (ex.: `1 3` = Claude Code, depois Gemini; a que não
     for digitada fica de fora), e o modelo e o effort de cada uma;
   - onde o bot funciona: **Moodle**, **Instagram** ou os dois;
   - **como conectar no Moodle:** só API, só extensão, *API e, se falhar, extensão* ou *extensão e, se
     falhar (porta ocupada), API*;
   - **como entrar no Instagram:** só senha (+2FA), só sessionid, *senha e, se falhar, sessionid* ou
     *sessionid e, se falhar, senha*;
   - o **reinício automático**;
   - por fim, **as chaves que essas escolhas precisam** (chave do Gemini, da Claude API, do Moodle, conta
     e senha do Instagram…). O que é segredo não aparece enquanto você digita; **Enter** mantém o valor
     atual (ou pula).

   Tudo fica no `.env` (as escolhas como `BOT_*`).
3. Manda uma mensagem de teste para **cada IA da linha** (gasta um pouco da cota). As que falharem viram
   aviso e **continuam na linha** (são tentadas de novo a cada mensagem); se nenhuma responder, não sobe.
4. **Testa as conexões**, só do que você escolheu: cada jeito do Moodle na ordem (chave da API, porta livre
   para a extensão) e o login do Instagram (mostrando qual jeito funcionou e se a reserva foi usada).

Se estiver tudo certo, sobe o bot. Se não, mostra o que falta e como resolver.

**Reserva com o bot rodando:** se o jeito atual do Moodle parar (ex.: a chave venceu no meio do uso), o bot
sobe o próximo da sequência sozinho. No Instagram, se a sessão cair, ele entra de novo seguindo a mesma
ordem de login.

**Reinício automático:** um vigia sobe o bot e confere a cada 30 s se ele está vivo. Se o bot cair ou travar
(servidor da extensão sem resposta por 2 min, ou Moodle/Instagram sem ler mensagens por 15 min), o vigia o
reinicia com as mesmas preferências. Se reiniciar 5 vezes em 10 min, desiste e mostra o erro. **Ctrl+C para
tudo.**

## Moodle pela API (sem extensão)

O bot conversa com o Moodle pela **API oficial** (os web services que o app Moodle do celular usa), com uma
**chave de acesso** da sua conta. Não precisa de extensão nem de navegador aberto.

### Pegar a chave

O login da UNIFEI é pelo gov.br, então o bot não consegue entrar com usuário e senha: ele usa a mesma chave
que o Moodle entrega ao app do celular. Você pega essa chave uma vez pelo navegador.

**No Chrome (ou Edge, Brave):**

1. Entre no [Moodle](https://moodle.unifei.edu.br) normalmente (pelo gov.br) e deixe a aba aberta.
2. Abra uma **aba nova** e aperte **F12** (abre as ferramentas do desenvolvedor).
3. Clique na aba **Rede** (*Network*) e marque **Preservar registro** (*Preserve log*).
4. Na barra de endereço dessa aba, cole este link e aperte Enter:

   ```
   https://moodle.unifei.edu.br/admin/tool/mobile/launch.php?service=moodle_mobile_app&passport=12345&urlscheme=moodlemobile
   ```

5. A página fica em branco ou o navegador pergunta se pode abrir um aplicativo externo (`xdg-open`,
   "Moodle"…): clique em **Cancelar**. Não precisa abrir nada.
6. Na lista da aba Rede, clique na linha **`launch.php`** → **Cabeçalhos** (*Headers*) → em
   **Cabeçalhos de resposta** (*Response Headers*), procure **`location`**. O valor começa com
   `moodlemobile://token=`. Selecione e copie esse valor inteiro.
   - Não achou? Digite `token` no campo de filtro da aba Rede e procure uma linha que comece com
     `moodlemobile://`.

**No Firefox:** igual, com estes nomes: **F12** → aba **Rede** → na engrenagem da aba, marque para
**manter os registros** (*Persist Logs*); depois do link, clique na linha `launch.php` → **Cabeçalhos** →
**Cabeçalhos da resposta** → `Location`.

**Use a chave:** rode `./start.sh --config` (ou o start da primeira vez), escolha Moodle pela API e cole o
`moodlemobile://token=…` quando o menu pedir a "Chave do Moodle" — exatamente como copiou: o bot extrai a
chave sozinho. A checagem do start deve mostrar:

```
✅ Moodle pela API como SEU NOME (sem extensão)
```

> **Outro Moodle (outra faculdade)?** O mesmo link funciona em qualquer Moodle com o app liberado: troque
> `moodle.unifei.edu.br` pelo endereço do seu, no link e no "Endereço do Moodle" do menu. Se a sua
> instituição desligou o app, use o [modo extensão](#moodle-pela-extensão).

### Onde mandar os comandos

O bot olha as suas **20 conversas mais recentes** e responde só aos comandos `!` que **você** escreveu, na
mesma conversa em que você escreveu:

- **Na conversa consigo mesmo (recomendado):** no Moodle, abra as mensagens (ícone de balão no topo) e
  procure a conversa com o **seu próprio nome** (o Moodle a deixa nos *Favoritos*). Ninguém mais vê o que
  está ali — é o lugar ideal para usar o bot.
- **Numa conversa com outra pessoa:** também funciona, mas a resposta aparece **para ela também**, e os
  comandos que ela mandar são ignorados (só os seus contam).

Ao subir, o bot ignora o que já estava nas conversas: só responde ao que chegar com ele rodando.

### A chave vence

- A chave dura um tempo definido pela instituição (semanas ou meses). Quando vencer, o start mostra
  `⚠️ Moodle: a chave (MOODLE_TOKEN) não vale mais` com o passo a passo; se vencer com o bot rodando, o bot
  passa para a reserva (se houver; senão, só a parte do Moodle para). Repita [Pegar a chave](#pegar-a-chave)
  e cole a nova no `./start.sh --config`.
- **A chave dá acesso à sua conta** como o app do celular: trate-a como a senha. Não mande para ninguém nem
  cole em chats. Se ela vazar, revogue no Moodle: *seu nome → Preferências → Chaves de segurança* →
  remova a do "Moodle mobile web service", e pegue outra.

### Código com `<` e `>` no modo API

O site do Moodle trata o que você digita como HTML: `#include <stdio.h>` ou `if (a<b && c>d)`, digitados
direto no site, chegam **cortados** (o próprio site apaga os trechos entre `<` e `>`). O bot percebe e
responde pedindo para reenviar, em vez de mandar código quebrado para a IA. Para enviar código assim:

- troque `<` por `&lt;`, `>` por `&gt;` e `&` por `&amp;` (ex.: `#include &lt;stdio.h&gt;`), ou
- mande pelo Instagram, ou
- use o [modo extensão](#moodle-pela-extensão), que faz essa troca sozinho ao enviar.

As **respostas** do bot sempre chegam intactas, com `<`, `>`, `&&` e indentação.

## As IAs e suas chaves

O bot tenta as IAs na ordem que você escolhe no menu (a **linha de reserva**). Se uma falhar (erro, cota
estourada, fora do ar), a próxima responde; na mensagem seguinte ele tenta de novo desde a primeira.

| IA | O que precisa | Custo |
|----|---------------|-------|
| **Claude Code (CLI)** | Instalar o Claude Code e rodar `claude` uma vez para logar | Usa a cota do seu plano do Claude (Pro/Max) |
| **Claude API** | A chave do [Console da Anthropic](https://console.anthropic.com/) (o menu pede) | Paga por uso |
| **Gemini** | A chave do [Google AI Studio](https://aistudio.google.com/apikey) (o menu pede) | Tem cota gratuita |

- No menu você também escolhe o **modelo** e o **effort** (quanto a IA pensa) do Claude, e o modelo inicial
  do Gemini (se ele falhar, o bot desce para os modelos seguintes da lista).
- Ponha na linha **só as IAs que você configurou**: uma IA sem chave falha em toda mensagem antes de passar
  para a próxima, deixando a resposta mais lenta.
- **Todas testam o código:** o Claude Code compila e roda sozinho; a Claude API e o Gemini recebem uma
  ferramenta que compila com `gcc -Wall -Wextra` + sanitizers e roda com as entradas que a IA escolher (até 8
  rodadas de testar e corrigir). Se o código ainda falhar nos testes, a resposta sai com um aviso.

## Usando os comandos

| Comando | Descrição |
|---------|-----------|
| `!chat <pergunta>` | Pergunta para a IA |
| `!fix <código>` | Pede a correção de um bug no código |
| `!chata <parte>` | Guarda uma parte de uma mensagem grande, sem chamar a IA |
| `!chatsend [texto]` | Junta as partes guardadas (e o texto, se houver) e envia como uma pergunta só |
| `!chclear` | Limpa a conversa (a IA esquece o histórico) |
| `!help` | Mostra todos os comandos |

**Conversa contínua:** `!chat` e `!fix` compartilham o mesmo histórico, como um chat normal. A IA recebe as
últimas 20 interações desde o último `!chclear` — não precisa repetir o código nem explicar de novo. Use
`!chclear` ao mudar de assunto, para a IA não misturar exercícios.

**Mensagem maior que o limite do chat** (o Moodle corta em ~4096 caracteres): mande em partes com
`!chata <parte 1>`, `!chata <parte 2>`… e finalize com `!chatsend o que você quer que eu faça?`.

**Rodar o seu código:** peça à IA, ex.: `!chat roda esse código com a entrada 5 e me mostra a saída`. Ela
compila e executa de verdade antes de responder.

**Respostas longas** chegam em várias mensagens numeradas `(1/3)`, `(2/3)`, `(3/3)`.

**Exemplos:**

```
!chat qual a diferença entre malloc e calloc?
!fix meu programa dá segmentation fault:
int main(void) { int *p; *p = 5; return 0; }
!chat agora faz uma versão que lê o tamanho do vetor do teclado
!chclear
```

### Execução direta (`!run`) — desativada

`!run <código C>`, `!r <valor>` e `!kill` compilavam e executavam o código direto, com entrada interativa.
Estão desativados por enquanto (respondem avisando); o código continua no projeto e testado. Para reativar,
mude `RUN_ATIVO = True` em `bot_moodle/comandos.py`.

## Instagram (opcional)

O bot também escuta uma DM do Instagram (a cada ~4–6 s), com os mesmos comandos e o mesmo histórico do
Moodle. Usa o [instagrapi](https://github.com/subzeroid/instagrapi). No menu, escolha "Moodle + Instagram"
ou "Só Instagram" e o jeito de entrar.

**Recomendações antes de configurar:**

- **Crie uma conta nova só para o bot**, em vez de usar a sua conta principal. O bot usa a API privada do
  app, contra os termos do Instagram, e a conta pode ser bloqueada ou cair em verificações; com uma conta
  própria do bot, quem corre esse risco é ela, não a sua.
- **Ative a autenticação de dois fatores por app autenticador** na conta do bot e informe a chave do
  autenticador quando o menu pedir: o bot gera o código sozinho a cada login. A chave é o código de texto
  que o Instagram mostra ao ativar o 2FA ("não consegue ler o QR code?"); os espaços não importam.
- **Anote os códigos de backup** (Configurações → Central de Contas → Senha e segurança → Autenticação de
  dois fatores → a conta → Métodos adicionais → Códigos de backup). Com eles você entra na conta em qualquer
  lugar sem precisar do celular com o autenticador: cada código vale uma vez, e usar um não desativa o
  autenticador nem desloga os outros aparelhos. Guarde-os num gerenciador de senhas, **nunca** no `.env`
  nem no repositório.

**Configurar:** rode `./start.sh --config`, escolha o Instagram e responda:

- a **conta do bot** e a **sua conta pessoal** (a DM em que o bot escuta e responde);
- o **jeito de entrar**: só senha, só sessionid, ou um e o outro como reserva;
- a **senha** e a chave do 2FA e/ou o **sessionid** (o que o jeito escolhido precisar).

Depois mande os comandos (`!chat`, `!fix`…) da **sua conta pessoal** para a conta do bot pela DM; ele
responde nessa conversa. (Também funciona com a própria conta do bot como DM: a conversa consigo mesmo.)

**Senha ou sessionid?**

- **Senha (+2FA):** o bot entra sozinho sempre que precisar. Às vezes o Instagram recusa o login com senha
  (`ClientNeedsUpgradeError`, verificação por e-mail) — por isso vale ter o sessionid como reserva.
- **Sessionid:** o cookie do navegador. Abra uma janela anônima, entre no instagram.com só com a conta do
  bot, copie o cookie `sessionid` (F12 → Aplicativo/Armazenamento → Cookies) e feche a janela **sem sair**
  (sair invalida o cookie). O bot confere se a sessão é mesmo da conta do bot e nunca usa outra.

**Bom saber:**

- A sessão fica em `dados/ig_session.json` para não logar com senha a cada início — trate-o como a senha.
- Respostas longas são quebradas em partes de até 900 bytes (o limite do Instagram é 1000 bytes por mensagem).
- Ao subir, o que já está na DM é ignorado: só responde comandos enviados com o bot rodando.
- Se o Instagram pedir checkpoint/verificação, o bot avisa e desliga só a parte do Instagram: confirme no
  app do Instagram e reinicie o bot.

## Moodle pela extensão

Uma extensão de navegador lê o chat aberto e manda as mensagens para o bot em `http://localhost:5000`. Use
se a sua instituição desligou o app do Moodle, como reserva da API, ou se você manda muito código com `<` e
`>` (a extensão escapa o texto ao enviar, então o código chega exato). No menu, escolha um dos jeitos com
**extensão**.

**Instalar a extensão** (os arquivos ficam na pasta `extensao/`):

- **Firefox:** `about:debugging` → *Este Firefox* → *Carregar extensão temporária* → escolha
  `extensao/manifest.json` (igual ao `manifest.firefox.json`). No Firefox, a extensão temporária some ao
  fechar o navegador.
- **Chrome:** copie `extensao/manifest.chrome.json` por cima de `extensao/manifest.json`, abra
  `chrome://extensions`, ative o *Modo do desenvolvedor* → *Carregar sem compactação* → escolha a pasta
  `extensao`.

**Usar:** com o bot rodando, abra o chat do Moodle no navegador e mande `!help`. A extensão só funciona com
o chat **aberto na tela** e responde a qualquer `!` desse chat.

## Variáveis do `.env`

O `.env` fica na raiz do projeto e é criado pelo menu — não precisa editar à mão. A referência completa
está em [`.env.example`](.env.example).

| Variável | Uso |
|----------|-----|
| `MOODLE_URL` / `MOODLE_TOKEN` | Moodle pela API: endereço do site e a chave do app ([ver](#pegar-a-chave)) |
| `API_KEY` | Chave do Gemini |
| `ANTHROPIC_API_KEY` | Chave da Claude API |
| `IG_USERNAME` / `IG_THREAD` | Conta do bot no Instagram e a DM que ele escuta (a sua conta pessoal) |
| `IG_PASSWORD` / `IG_TOTP_SEED` | Senha da conta do bot e a chave do 2FA (login por senha) |
| `IG_SESSIONID` | Cookie `sessionid` do navegador (login por sessionid) |
| `BOT_IAS`, `BOT_*_MODELO`, `BOT_*_EFFORT` | A linha de IAs e os modelos |
| `BOT_PLATAFORMAS` | `moodle`, `instagram` ou os dois |
| `BOT_MOODLE_MODOS` | `api` e/ou `extensao`, na ordem da reserva (ex.: `api,extensao`) |
| `BOT_IG_LOGIN` | `senha` e/ou `sessionid`, na ordem da reserva |
| `BOT_VIGIA` | `1` liga o reinício automático |
| `BOT_CONFIGURADO` | `1` depois que o menu foi concluído (sem ele, o menu abre sozinho) |
| `DB_FILE` | Onde fica o banco (padrão `dados/moodle_history.duckdb`) |
| `PORT` | Porta do modo extensão (padrão 5000; a extensão espera 5000) |

## Problemas comuns

| O que aparece | O que fazer |
|---------------|-------------|
| `⚠️ Moodle: a chave (MOODLE_TOKEN) não vale mais` | A chave venceu ou foi revogada: [pegue outra](#pegar-a-chave) e cole no `./start.sh --config`. |
| `⚠️ Moodle pela API escolhido, mas falta MOODLE_TOKEN` | Rode `./start.sh --config` e cole a chave, ou escolha o modo extensão. |
| O `launch.php` volta para a tela de login | Entre no Moodle primeiro, na mesma janela, e abra o link de novo. |
| Mando `!chat` no Moodle e nada acontece | Confira se o bot está rodando, se a mensagem começa com `!` e se foi **você** que mandou. Comandos enviados antes de o bot subir são ignorados. |
| A resposta pede para reenviar trocando `<` por `&lt;` | Veja [Código com `<` e `>`](#código-com--e--no-modo-api). |
| `⚠️ Claude API … Could not resolve authentication method` | Falta a chave da Claude API: cole no `--config` ou tire a Claude API da linha. |
| `❌ Nenhuma IA da linha respondeu ao teste` | Veja os avisos de cada IA acima dela. Rode `claude` para logar no Claude Code ou confira as chaves. |
| `Gemini … 503 UNAVAILABLE` | Sobrecarga passageira do Google; o bot já tenta o próximo modelo da lista. |
| `Instagram: o login por senha … (foi para a reserva)` | A senha foi recusada e o bot entrou pelo sessionid. Confira a senha/2FA ou deixe só o sessionid. |
| `Instagram não logou` | Veja a causa na linha; se for verificação, confirme no app do Instagram. |
| `Porta 5000 já está em uso` | Outro bot já está rodando: feche-o. No macOS, desligue o Receptor AirPlay. Com a API como reserva, o bot usa ela. |
| `desistindo para não ficar em loop` | O bot caiu 5 vezes em 10 min: leia os erros acima dessa linha. |
| Windows: comando não encontrado logo depois de instalar | Feche o terminal, abra outro e rode o `start.bat` de novo. |

## Segurança

- **Guarde bem o `.env`** (chave do Moodle, chaves das IAs, senha e chave do 2FA do Instagram) e a pasta
  `dados/` (banco e sessões do Instagram). Eles estão no `.gitignore`: não vão para o GitHub. Não os envie
  para ninguém.
- A chave do Moodle dá acesso à sua conta: se vazar, revogue em *Preferências → Chaves de segurança*.
- Os testes que a IA faz (e o `!run`, se reativado) **executam código na sua máquina**, com o seu usuário.
  No modo extensão, qualquer pessoa no chat aberto pode mandar comandos; no modo API, só os seus contam.
- O Instagram é usado pela API privada do app, contra os termos de uso: use uma conta própria do bot.

## Estrutura do projeto

```
moodleChat/
├── start.sh · start.bat     # verificam o ambiente, abrem o menu, testam as conexões e sobem o bot
├── pyproject.toml           # o projeto Python (dependências, pytest, pylint)
├── .env.example             # referência do .env (o menu cria o .env de verdade)
├── bot_moodle/              # o código do bot
│   ├── app.py               # ponto de entrada: sobe as plataformas escolhidas, com reserva
│   ├── comandos.py          # os comandos do chat (!chat, !fix, !chata…), numa tabela
│   ├── db.py                # o banco (histórico, runs, buffer do !chata)
│   ├── caminhos.py          # onde ficam o .env e a pasta dados/
│   ├── ia/                  # as IAs: linha de reserva, Claude Code, Claude API, Gemini, testador de C
│   ├── plataformas/         # Moodle pela API, servidor da extensão, Instagram
│   ├── inicio/              # o menu, as checagens do start e o vigia
│   └── execucao/            # o !run (compilar e rodar C) e a reconstrução dos #include
├── tests/                   # os testes (pytest), na mesma estrutura de bot_moodle/
├── extensao/                # a extensão do navegador (e os testes dela em extensao/tests/)
├── docs/                    # arquitetura e guia de desenvolvimento
└── dados/                   # criado pelo bot: banco e sessões (fora do git)
```

## Desenvolvimento

O projeto é desenvolvido com **TDD**: cada comportamento tem um teste que o descreve, escrito antes (ou junto)
do código. Os testes simulam o Moodle, o Instagram e as IAs: não precisam de chave, senha nem internet, e
cada um roda numa pasta temporária (nunca tocam o seu `.env` nem o seu banco).

```bash
.venv/bin/pip install -e ".[dev]"      # Windows: .venv\Scripts\pip install -e ".[dev]"
.venv/bin/pytest                       # todos os testes (~20 s); os que compilam C são pulados sem gcc
.venv/bin/pytest tests/ia              # só os de uma parte (a pasta espelha bot_moodle/)
.venv/bin/pylint bot_moodle            # o CI exige nota >= 9.5
node --test "extensao/tests/*.test.js" # os testes da extensão
```

A cada envio e a cada PR, o **CI do GitHub** roda os testes no Linux, no macOS e no Windows, o pylint, os
testes da extensão e a checagem do `start.sh`. O passo a passo (como escrever um teste, adicionar um
comando, o que o CI faz) está em [docs/desenvolvimento.md](docs/desenvolvimento.md); como as partes se
encaixam, em [docs/arquitetura.md](docs/arquitetura.md).
