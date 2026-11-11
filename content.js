// content.js - Manipulação direta do DOM (I/O)

console.log("[Bot] Camada de interface (content.js) iniciada! 🚀");

// Limite usado quando o textarea não declara maxlength.
// O chat do Moodle corta em 4096 caracteres (medido); folga para \n / acentos contados diferente no servidor.
const LIMITE_PADRAO = 3000;
const TIMEOUT_ENVIO_MS = 15000; // teto de espera por parte enviada
const RESERVA_PREFIXO = 10; // espaço para "(12/34) "

const dormir = (ms) => new Promise((r) => setTimeout(r, ms));

const SELETOR_CAMPO = 'textarea[data-region="send-message-txt"]';
const SELETOR_BOTAO = 'button[data-action="send-message"]';

/**
 * O Moodle interpreta a mensagem como HTML: "<stdio.h>" ou "a<b && c>d" viram tag e somem.
 * Escapando antes de enviar, ele guarda as entidades e mostra o texto exato
 * (e o innerText que o bot lê volta com os "<" originais).
 */
function escaparHtml(texto) {
    return texto.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function desescaparHtml(texto) {
    return texto.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
}

/**
 * Quebra o texto (já escapado) em partes <= limite, preferindo cortar em quebra de linha,
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
        if (corte < max / 2) {
            corte = max;
            // Não corta uma entidade (&amp; tem até 5 chars) no meio
            const amp = resto.lastIndexOf("&", corte - 1);
            if (amp > corte - 6 && resto.indexOf(";", amp) >= corte) corte = amp;
        }
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
let enviandoBot = false; // o texto do bot já vai escapado; o listener de envio não mexe

async function enviarMensagem(texto) {
    const campoTexto = document.querySelector(SELETOR_CAMPO);
    const botaoEnviar = document.querySelector(SELETOR_BOTAO);

    if (!campoTexto || !botaoEnviar) return;

    // Divide depois de escapar: o limite do Moodle conta o texto escapado
    const partes = dividirMensagem(escaparHtml(texto), limiteDoCampo(campoTexto));
    enviandoBot = true;
    try {
        for (const parte of partes) {
            campoTexto.value = parte;
            campoTexto.dispatchEvent(new Event("input", { bubbles: true }));
            await dormir(50);
            botaoEnviar.click();
            await esperarEnvio(campoTexto, botaoEnviar);
        }
    } finally {
        enviandoBot = false;
    }
}

/**
 * Escapa o que o usuário digitou logo antes do Moodle enviar (Enter ou botão).
 * Desescapa antes para ser idempotente (ex.: Enter que não chegou a enviar + botão).
 * ponytail: quem digitar "&lt;" literal verá "<"; aceitável num chat de código.
 */
function escaparCampoDoUsuario() {
    const campo = document.querySelector(SELETOR_CAMPO);
    if (enviandoBot || !campo || !campo.value) return;
    campo.value = escaparHtml(desescaparHtml(campo.value));
}

// Fase de captura: roda antes dos handlers do Moodle, que leem o campo para enviar
document.addEventListener(
    "click",
    (e) => {
        if (e.target.closest?.(SELETOR_BOTAO)) escaparCampoDoUsuario();
    },
    true,
);
document.addEventListener(
    "keydown",
    (e) => {
        // Só quando o "Enter para enviar" do Moodle está ligado; senão o Enter só pula linha
        const enterEnvia = document.querySelector(
            '[data-preference="entertosend"] input[type="checkbox"]',
        )?.checked;
        if (enterEnvia && e.key === "Enter" && !e.shiftKey && e.target.matches?.(SELETOR_CAMPO)) {
            escaparCampoDoUsuario();
        }
    },
    true,
);

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

/**
 * O Moodle guarda a indentação ("<br>\n    código"), mas o HTML junta os espaços na tela.
 * Tira o "\n" depois de cada <br> (senão vira linha dupla) e liga pre-wrap: o código
 * aparece indentado e o innerText (o que o bot lê) mantém os espaços. Idempotente.
 */
function preservarIndentacao(p) {
    for (const n of p.childNodes) {
        if (n.nodeType === Node.TEXT_NODE && n.previousSibling?.nodeName === "BR") {
            n.textContent = n.textContent.replace(/^\n/, "");
        }
    }
    p.style.whiteSpace = "pre-wrap";
}

async function varrerChat() {
    // Seleciona apenas mensagens que NÃO possuem o atributo customizado 'data-bot-checked'
    const novasMensagens = document.querySelectorAll(
        '[data-region="message"]:not([data-bot-checked])',
    );
    if (novasMensagens.length === 0) return;

    for (const msg of novasMensagens) {
        const id = msg.getAttribute("data-message-id");
        const paragrafo = msg.querySelector('[data-region="text-container"] p');
        if (paragrafo) preservarIndentacao(paragrafo);
        const texto = paragrafo?.innerText?.trim();

        // Mensagem recém-enviada nasce com id "temp…" (e às vezes sem texto) e o Moodle
        // troca pelo id real no mesmo elemento: espera o próximo ciclo em vez de marcar.
        // Processar com o id temp quebraria o dedup (reprocessa ao recarregar a página).
        if (!id || id.startsWith("temp") || !texto) continue;

        // Marca o elemento para o próximo ciclo ignorá-lo
        msg.setAttribute("data-bot-checked", "true");

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
