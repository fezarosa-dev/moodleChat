// Testes das funções de texto da extensão: node --test extensao/tests/
const test = require("node:test");
const assert = require("node:assert/strict");
const { escaparHtml, desescaparHtml, dividirMensagem, RESERVA_PREFIXO } = require("../texto.js");

const semPrefixo = (parte) => parte.replace(/^\(\d+\/\d+\) /, "");

test("escapa o que o Moodle trataria como HTML", () => {
    assert.equal(escaparHtml("#include <stdio.h> a<b && c>d"), "#include &lt;stdio.h&gt; a&lt;b &amp;&amp; c&gt;d");
});

test("desescapar volta o texto original", () => {
    const codigo = 'if (a<b && c>d) printf("&");';
    assert.equal(desescaparHtml(escaparHtml(codigo)), codigo);
});

test("mensagem curta vai inteira, sem numeração", () => {
    assert.deepEqual(dividirMensagem("oi", 100), ["oi"]);
});

test("mensagem longa vira partes numeradas dentro do limite", () => {
    const texto = Array.from({ length: 50 }, (_, i) => `linha ${i} com algum texto`).join("\n");
    const partes = dividirMensagem(texto, 200);
    assert.ok(partes.length > 1);
    assert.ok(partes.every((p) => p.length <= 200));
    assert.match(partes[0], new RegExp(`^\\(1/${partes.length}\\) `));
});

test("corta em quebra de linha e juntando as partes volta o texto", () => {
    const texto = Array.from({ length: 50 }, (_, i) => `linha ${i}`).join("\n");
    assert.equal(dividirMensagem(texto, 100).map(semPrefixo).join("\n"), texto);
});

test("sem quebra de linha, corta no espaço", () => {
    const texto = "palavra ".repeat(100).trim();
    assert.ok(dividirMensagem(texto, 100).every((p) => !semPrefixo(p).startsWith(" ")));
    assert.equal(dividirMensagem(texto, 100).map(semPrefixo).join(" "), texto);
});

test("não corta uma entidade como &amp; no meio", () => {
    const texto = escaparHtml("&".repeat(300));
    for (const parte of dividirMensagem(texto, 50)) {
        assert.match(semPrefixo(parte), /^(&amp;)+$/);
    }
});

test("nenhuma parte começa com ! (não vira comando de novo)", () => {
    const texto = "!".repeat(500);
    assert.ok(dividirMensagem(texto, 100).every((p) => p.startsWith("(")));
    assert.ok(RESERVA_PREFIXO >= "(99/99) ".length);
});
