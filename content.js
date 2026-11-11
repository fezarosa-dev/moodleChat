// content.js - Manipulação direta do DOM (I/O)

console.log("[Bot] Camada de interface (content.js) iniciada! 🚀");

// Limite usado quando o textarea não declara maxlength.
// O chat do Moodle corta em 4096 caracteres (medido); folga para \n / acentos contados diferente no servidor.
const LIMITE_PADRAO = 3000;
const TIMEOUT_ENVIO_MS = 15000; // teto de espera por parte enviada
const RESERVA_PREFIXO = 10; // espaço para "(12/34) "

const dormir = (ms) => new Promise((r) => setTimeout(r, ms));

/**
 * Quebra o texto em partes <= limite, preferindo cortar em quebra de linha,
 * depois em espaço, e só em último caso no meio da palavra.
 * Com mais de uma parte, prefixa "(i/n) " — isso também impede que uma parte
 * comece com "!" e seja reprocessada como comando.
 */
function dividirMensagem(texto, limite) {
    const max = limite - RESERVA_PREFIXO;
    const partes = [];
    let resto = texto;
    while (resto.length > max) {
        let corte = resto.lastIndexOf("\n", max);
        if (corte < max / 2) corte = resto.lastIndexOf(" ", max);
        if (corte < max / 2) corte = max;
        partes.push(resto.slice(0, corte));
        resto = resto.slice(corte).replace(/^[\n ]/, "");
    }
    partes.push(resto);
    if (partes.length === 1) return partes;
    return partes.map((p, i) => `(${i + 1}/${partes.length}) ${p}`);
}

function limiteDoCampo(campo) {
    return campo.maxLength > 0 ? campo.maxLength : LIMITE_PADRAO;
}

/**
 * Insere o texto no chat e envia, quebrando em várias mensagens se necessário
 */
async function enviarMensagem(texto) {
    const campoTexto = document.querySelector(
        'textarea[data-region="send-message-txt"]',
    );
    const botaoEnviar = document.querySelector(
        'button[data-action="send-message"]',
    );

    if (!campoTexto || !botaoEnviar) return;

    for (const parte of dividirMensagem(texto, limiteDoCampo(campoTexto))) {
        campoTexto.value = parte;
        campoTexto.dispatchEvent(new Event("input", { bubbles: true }));
        await dormir(50);
        botaoEnviar.click();
        await esperarEnvio(campoTexto, botaoEnviar);
    }
}

/**
 * Espera o Moodle concluir o envio (campo esvaziado e botão liberado) antes
 * da próxima parte, com teto para não travar se o DOM mudar.
 */
async function esperarEnvio(campo, botao) {
    const inicio = Date.now();
    while (Date.now() - inicio < TIMEOUT_ENVIO_MS) {
        await dormir(200);
        if (campo.value === "" && !botao.disabled) break;
    }
    await dormir(300); // folga para o Moodle renderizar a mensagem enviada
}

let ocupado = false; // evita que um ciclo novo intercale envio com outro em andamento

/**
 * Monitora o chat selecionando APENAS elementos que não foram checados ainda (:not)
 * Isso economiza RAM e evita overhead de CPU processando loops infinitos
 */
async function monitorarChat() {
    if (ocupado) return;
    ocupado = true;
    try {
        await varrerChat();
    } finally {
        ocupado = false;
    }
}

async function varrerChat() {
    // Seleciona apenas mensagens que NÃO possuem o atributo customizado 'data-bot-checked'
    const novasMensagens = document.querySelectorAll(
        '[data-region="message"]:not([data-bot-checked])',
    );
    if (novasMensagens.length === 0) return;

    for (const msg of novasMensagens) {
        // Marca o elemento imediatamente no HTML para o próximo ciclo ignorá-lo
        msg.setAttribute("data-bot-checked", "true");

        const id = msg.getAttribute("data-message-id");
        const texto = msg
            .querySelector('[data-region="text-container"] p')
            ?.innerText?.trim();

        if (!id || !texto) continue;

        // Se o módulo chatUsage estiver pronto no escopo global, envia o dado para processamento
        if (window.ChatUsage) {
            const resposta = await window.ChatUsage.processarMensagem(
                id,
                texto,
            );

            if (resposta) {
                await enviarMensagem(resposta);
            }
        }
    }
}

// Executa a varredura visual a cada 2 segundos
setInterval(monitorarChat, 2000);
