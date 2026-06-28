# moodleChat
AI agent and tools for moodle chat


Funciona atualmente somente com a API do gemini.
Funciona atualmente somente com o Firefox, não testado em outros navegadores.
Para rodar precisa ter python instalado, duckdb, firefox, gcc.

Para rodar o projeto, siga os seguintes passos:
1. Clone o repositório:
   ```bash
   git clone repo_url
    ```
2. Navegue até o diretório do projeto:
   ```bash
   cd moodleChat
   ```
3. Instale as dependências:
   ```bash
   pip install -r bot_moodle_backend/requirements.txt
   ```
3.1 Instale o gcc, caso não tenha.
3.2 Instale o Firefox, caso não tenha.
4. Configure as variáveis de ambiente:
   - Crie um arquivo `.env` na raiz do projeto.
   - Adicione as seguintes variáveis de ambiente no arquivo `.env`:
        ```
        API_KEY=your_api_key
        ```
    - Abra o arquivo chatUsage.js e configure a variável `NOME_AUTORIZADO` com o seu nome de usuário do Moodle.
5. Execute o backend:
   ```bash
   python3 bot_moodle_backend/server.py
   ```
6. Abra o navegador e acesse
    ```txt
    about:debugging#/runtime/this-firefox
    ```
7. Clique em "Load Temporary Add-on" e selecione o arquivo `manifest.json`.
8 . Abra o Moodle e faça login.
9. Clique para abrir as conversas, busque em contatos seu propio nome e clique para abrir a conversa (recomendo salvar com estrela a conversa).
10. Confirme se a extenssão tem todas as permissões.
11. Digite !help na conversa para ver os comandos disponíveis.
12. Para usar o bot, a aba de conversa deve estar aberta, o server.py precisa estar rodando, ou seja se sair da aba do moodle, o bot não ira responder, do jeito que foi desenvolvido, ele não consegue ler as mensagens se a aba estiver em segundo plano.
13. Para usar o bot em um computador ou celular difrente, basta que o bot eseja funcionando em um outro notbook ou pc seu, e que estejam usando o mesmo usuario nos 2, entao só abrir a conversa e utilizar o bot, então para rodar em outro lugar voce precisa de um computador ligado.

Para mudar o estilo de resposta do bot, abra o arquivo server.py e altere conforme desejado, atualemnte ele esta focado em responder perguntas de programacao, tabem esta configurado para subisituir o "<>" do #include do c por "[]" pois o moodle nao permite o "<>", entao até quando utilizar o comando !run, lembre-se de alterar o codigo para utilizar "[]" no lugar de "<>", caso contrario o bot ira retornar erro de compilacao. Caso precise adiconar uma biblioteca nova que ainda nao esteja no run.py só modificar a variavel `_HEADERS_INFERIDOS` adicionando a biblioteca desejada.

O prompt esta configurado para responder de forma resumida, ou seja nao fornecera explicacoes a menos que seja solicitado.


O seu chat continuara funcionando normalmente, pois no bot esta configurado para apenas ler mensagens da conversa configurada conmo NOME_AUTORIZADO, e responder apenas a mensagens que comecem com "!".


Ao usar o !run e !r, pode ocorrer do output do programa nao ser retornado automaticamente, para isso é só digitar qualquer novo input com !r.


O historico das conversas com a IA, é armazenado em um arquivo na pasta `bot_moodle_backend`, ele faz esse armazenamento para que seja possivel utilizar contexto (lembrando que o contexto é selecionando conforme sua preferencia ao ustilizar o comando !chat), TOME CUIDADO pois ao utilizar contextos extensos ira utilizar mais tokens, recomendo cautela e utilziar somente qunando necessario, sempre que quiser limpar o contexto completamente, só apagar o arquivo de bd,e reiniciar o server.py, ele ira criar um novo arquivo de bd vazio. O historico de conversas é ilimitado, pois é armazenado 100% localmente, ou seja quanto caber no seu pc, voce pode ter de historico.
