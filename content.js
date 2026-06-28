// content.js - Manipulação direta do DOM (I/O)

console.log("[Bot] Camada de interface (content.js) iniciada! 🚀");

/**
 * Função pura de inserção e envio de dados no chat
 */
function enviarMensagem(texto) {
    const campoTexto = document.querySelector('textarea[data-region="send-message-txt"]');
    const botaoEnviar = document.querySelector('button[data-action="send-message"]');

    if (!campoTexto || !botaoEnviar) return;

    campoTexto.value = texto;
    campoTexto.dispatchEvent(new Event('input', { bubbles: true }));

    setTimeout(() => {
        botaoEnviar.click();
    }, 50);
}

/**
 * Monitora o chat selecionando APENAS elementos que não foram checados ainda (:not)
 * Isso economiza RAM e evita overhead de CPU processando loops infinitos
 */
async function monitorarChat() {
    // Seleciona apenas mensagens que NÃO possuem o atributo customizado 'data-bot-checked'
    const novasMensagens = document.querySelectorAll('[data-region="message"]:not([data-bot-checked])');
    if (novasMensagens.length === 0) return;

    for (const msg of novasMensagens) {
        // Marca o elemento imediatamente no HTML para o próximo ciclo ignorá-lo
        msg.setAttribute('data-bot-checked', 'true');

        const id = msg.getAttribute('data-message-id');
        const texto = msg.querySelector('[data-region="text-container"] p')?.innerText?.trim();

        if (!id || !texto) continue;

        // Se o módulo chatUsage estiver pronto no escopo global, envia o dado para processamento
        if (window.ChatUsage) {
            const resposta = await window.ChatUsage.processarMensagem(id, texto);

            if (resposta) {
                enviarMensagem(resposta);
            }
        }
    }
}

// Executa a varredura visual a cada 2 segundos
setInterval(monitorarChat, 2000);
