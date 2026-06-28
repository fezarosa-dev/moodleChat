// chatUsage.js - Processamento de Dados e Regras de Negócio
const ChatUsage = {
    BACKEND_URL: 'http://localhost:5000/check_and_save',

    NOME_AUTORIZADO: 'FELIPE ZANONI DA ROSA',

    /**
     * Retorna o nome do usuário logado no Moodle (em maiúsculas, sem espaços extras).
     * Usa múltiplos seletores estáveis em ordem de confiabilidade,
     * sem depender de IDs dinâmicos (yui_*) nem posições absolutas de XPath.
     */
    _obterNomeUsuario() {
        const tentativas = [
            // 1. Strong com classes específicas dentro do drawer de mensagens
            //    (estrutura semântica do tema Moodle — muito estável)
            () => document.querySelector('.message-app strong.m-0.text-truncate'),

            // 2. Strong dentro do header-container do message-drawer
            () => document.querySelector('[id^="message-drawer"] strong.m-0.text-truncate'),

            // 3. Qualquer strong.m-0.text-truncate dentro de .header-container
            () => document.querySelector('.header-container strong.m-0.text-truncate'),

            // 4. Fallback genérico: primeiro strong com essas classes na página
            () => document.querySelector('strong.m-0.text-truncate'),
        ];

        for (const tentar of tentativas) {
            try {
                const el = tentar();
                if (el) {
                    const nome = el.textContent.trim().toUpperCase();
                    if (nome.length > 2) return nome; // descarta resultados vazios/ruins
                }
            } catch (_) { /* seletor inválido no contexto atual, tenta o próximo */ }
        }

        return null;
    },

    /**
     * Valida a mensagem no DuckDB e retorna a resposta da IA caso exista.
     * Só processa se:
     *   1. O usuário logado for FELIPE ZANONI DA ROSA
     *   2. A mensagem começar com '!'
     *
     * @param {string} id    - ID da mensagem do Moodle
     * @param {string} texto - Conteúdo da mensagem
     * @returns {Promise<string|null>}
     */
    async processarMensagem(id, texto) {
        // ── Guarda 1: usuário autorizado ──────────────────────────────────────
        const nome = this._obterNomeUsuario();
        if (nome !== this.NOME_AUTORIZADO) return null;

        // ── Guarda 2: apenas comandos (mensagens que começam com '!') ─────────
        const textoTrimado = texto.trim();
        if (!textoTrimado.startsWith('!')) return null;

        // ── Envia para o backend ───────────────────────────────────────────────
        try {
            const respostaDb = await fetch(this.BACKEND_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id: id, texto: textoTrimado })
            });

            const resultadoDb = await respostaDb.json();

            if (resultadoDb.status !== 'new') return null;

            if (resultadoDb.is_command && resultadoDb.resposta) {
                return resultadoDb.resposta;
            }

            return null;
        } catch (erro) {
            console.error("[ChatUsage] Erro ao processar mensagem no cérebro:", erro);
            return null;
        }
    }
};

// Vincula o objeto ao escopo global (window)
window.ChatUsage = ChatUsage;
