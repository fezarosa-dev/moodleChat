// texto.js - Funções puras de texto (sem DOM): escapar o HTML e dividir mensagens longas.
// Carregado antes do content.js (manifest.json) e testado no Node (extensao/tests/).

const RESERVA_PREFIXO = 10; // espaço para "(12/34) "

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
        const corte = ondeCortar(resto, max);
        partes.push(resto.slice(0, corte));
        resto = resto.slice(corte).replace(/^[\n ]/, "");
    }
    partes.push(resto);
    if (partes.length === 1) return partes;
    return partes.map((parte, i) => `(${i + 1}/${partes.length}) ${parte}`);
}

/**
 * Onde cortar: na última quebra de linha da metade de trás; senão no último espaço; senão no
 * limite, sem partir uma entidade no meio (&amp; tem até 5 caracteres).
 */
function ondeCortar(texto, max) {
    for (const separador of ["\n", " "]) {
        const corte = texto.lastIndexOf(separador, max);
        if (corte >= max / 2) return corte;
    }
    const inicioDaEntidade = texto.lastIndexOf("&", max - 1);
    const entidadeNoMeio = inicioDaEntidade > max - 6 && texto.indexOf(";", inicioDaEntidade) >= max;
    return entidadeNoMeio ? inicioDaEntidade : max;
}

// No navegador as funções ficam globais para o content.js; no Node, os testes as importam.
if (typeof module !== "undefined") {
    module.exports = { escaparHtml, desescaparHtml, dividirMensagem, RESERVA_PREFIXO };
}
