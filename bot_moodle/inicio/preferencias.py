"""O menu do start: as escolhas do bot (IAs, plataformas, jeitos de conectar, vigia) e as chaves
que elas precisam, salvas no .env.

`python -m bot_moodle.inicio.preferencias [--config]`: mostra as escolhas e, se pedido (ou se é a
primeira vez, sem BOT_CONFIGURADO no .env), abre o menu.
"""

import getpass
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from bot_moodle import caminhos

IAS = {"claude_cli": "Claude Code (CLI)", "claude_api": "Claude API", "gemini": "Gemini"}
PLATAFORMAS = {"moodle": "Moodle", "instagram": "Instagram"}
MODOS_MOODLE = {"api": "API", "extensao": "extensão"}
LOGINS_INSTAGRAM = {"senha": "senha", "sessionid": "sessionid"}
EFFORTS = ["low", "medium", "high", "xhigh", "max"]
# o Gemini desce esta lista a partir do modelo escolhido quando um falha (ex.: cota)
MODELOS_GEMINI = [
    "gemini-3.8-flash",
    "gemini-3.5-flash",
    "gemini-3-flash-preview",
    "gemini-2.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
]

PADROES = {
    "BOT_IAS": "claude_cli,gemini",          # linha de reserva das IAs, na ordem
    "BOT_CLI_MODELO": "opus",
    "BOT_CLI_EFFORT": "medium",
    "BOT_API_MODELO": "claude-sonnet-5-5",
    "BOT_API_EFFORT": "medium",
    "BOT_GEMINI_MODELO": "gemini-3.5-flash",
    "BOT_PLATAFORMAS": "moodle,instagram",
    "BOT_MOODLE_MODOS": "api,extensao",      # o primeiro que funcionar; os outros são reserva
    "BOT_IG_LOGIN": "senha,sessionid",       # idem
    "BOT_VIGIA": "1",
    "BOT_CONFIGURADO": "",                   # "1" depois do menu: sem ele, é a primeira vez
}
LEGADO = {"BOT_MOODLE_MODOS": "BOT_MOODLE_MODO"}  # nomes antigos que ainda valem
OPCOES = {
    "BOT_CLI_MODELO": ["opus", "sonnet", "haiku"],
    "BOT_CLI_EFFORT": EFFORTS,
    "BOT_API_MODELO": ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"],
    "BOT_API_EFFORT": EFFORTS,
    "BOT_GEMINI_MODELO": MODELOS_GEMINI,
    "BOT_PLATAFORMAS": ["moodle,instagram", "moodle", "instagram"],
    "BOT_MOODLE_MODOS": ["api", "extensao", "api,extensao", "extensao,api"],
    "BOT_IG_LOGIN": ["senha", "sessionid", "senha,sessionid", "sessionid,senha"],
    "BOT_VIGIA": ["1", "0"],
}
ROTULOS = {
    "moodle,instagram": "Moodle + Instagram", "moodle": "Só Moodle", "instagram": "Só Instagram",
    "1": "Sim", "0": "Não",
    "api": "Só pela API (chave MOODLE_TOKEN, sem extensão)",
    "extensao": "Só pela extensão do navegador (servidor na porta 5000)",
    "api,extensao": "API; se ela falhar, extensão",
    "extensao,api": "Extensão; se ela falhar (porta ocupada), API",
    "senha": "Só usuário e senha (+ 2FA pelo IG_TOTP_SEED)",
    "sessionid": "Só o cookie sessionid do navegador",
    "senha,sessionid": "Senha; se ela falhar, sessionid",
    "sessionid,senha": "Sessionid; se ele falhar, senha",
}
TITULOS = {
    "BOT_CLI_MODELO": "Claude Code: modelo", "BOT_CLI_EFFORT": "Claude Code: effort",
    "BOT_API_MODELO": "Claude API: modelo", "BOT_API_EFFORT": "Claude API: effort",
    "BOT_GEMINI_MODELO": "Gemini: modelo inicial",
    "BOT_PLATAFORMAS": "Onde o bot funciona",
    "BOT_MOODLE_MODOS": "Como o bot fala com o Moodle",
    "BOT_IG_LOGIN": "Como o bot entra no Instagram",
    "BOT_VIGIA": "Reiniciar sozinho se cair ou travar",
}
# o que cada IA deixa escolher no menu
AJUSTES = {
    "claude_cli": ["BOT_CLI_MODELO", "BOT_CLI_EFFORT"],
    "claude_api": ["BOT_API_MODELO", "BOT_API_EFFORT"],
    "gemini": ["BOT_GEMINI_MODELO"],
}
ENV = caminhos.ENV


@dataclass(frozen=True)
class Chave:
    """Um valor do .env que o menu pede (Enter mantém o atual ou pula)."""

    nome: str
    rotulo: str
    segredo: bool = True     # não aparece na tela enquanto é digitado
    ajuda: str = ""
    padrao: str = ""


# as chaves que cada escolha precisa
CHAVES = {
    "claude_api": [Chave("ANTHROPIC_API_KEY", "Chave da Claude API", ajuda="console.anthropic.com → API Keys")],
    "gemini": [Chave("API_KEY", "Chave do Gemini", ajuda="aistudio.google.com/apikey")],
    "moodle:api": [
        Chave("MOODLE_URL", "Endereço do Moodle", segredo=False, padrao="https://moodle.unifei.edu.br"),
        Chave("MOODLE_TOKEN", "Chave do Moodle (o moodlemobile://token=… inteiro)",
              ajuda="como pegar: README, seção \"Pegar a chave\""),
    ],
    "instagram": [
        Chave("IG_USERNAME", "Instagram: usuário da conta do bot", segredo=False),
        Chave("IG_THREAD", "Instagram: usuário da DM que o bot escuta (a sua conta pessoal)", segredo=False),
    ],
    "instagram:senha": [
        Chave("IG_PASSWORD", "Instagram: senha da conta do bot"),
        Chave("IG_TOTP_SEED", "Instagram: chave do app autenticador (2FA), se tiver"),
    ],
    "instagram:sessionid": [
        Chave("IG_SESSIONID", "Instagram: cookie sessionid", ajuda="como pegar: README, seção Instagram"),
    ],
}


# ── ler as escolhas ──────────────────────────────────────────────────────────

def pref(nome: str) -> str:
    """O valor da escolha (do .env ou do ambiente), ou o padrão."""
    return os.getenv(nome) or os.getenv(LEGADO.get(nome, "")) or PADROES[nome]


def lista(nome: str) -> list[str]:
    """A escolha em lista (ex.: BOT_IAS="claude_cli,gemini" -> ["claude_cli", "gemini"])."""
    return [valor for valor in pref(nome).split(",") if valor]


def primeira_vez() -> bool:
    """O menu nunca foi concluído (falta BOT_CONFIGURADO=1 no .env)."""
    return pref("BOT_CONFIGURADO") != "1"


def _sequencia(nome: str, rotulos: dict) -> str:
    return " → ".join(rotulos.get(valor, valor) for valor in lista(nome))


def resumo() -> str:
    """As escolhas atuais, em texto para o menu."""
    ias = " → ".join(f"{IAS[ia]} ({', '.join(pref(a) for a in AJUSTES[ia])})"
                     for ia in lista("BOT_IAS") if ia in IAS)
    detalhes = {"moodle": f" ({_sequencia('BOT_MOODLE_MODOS', MODOS_MOODLE)})",
                "instagram": f" ({_sequencia('BOT_IG_LOGIN', LOGINS_INSTAGRAM)})"}
    plataformas = " + ".join(PLATAFORMAS[p] + detalhes[p] for p in lista("BOT_PLATAFORMAS") if p in PLATAFORMAS)
    vigia = "ligado" if pref("BOT_VIGIA") == "1" else "desligado"
    return (f"   IAs (na ordem de reserva): {ias or 'nenhuma'}\n"
            f"   Plataformas: {plataformas or 'nenhuma'}\n"
            f"   Reinício automático se cair ou travar: {vigia}")


# ── perguntas ────────────────────────────────────────────────────────────────

def _perguntar(texto: str, atual: str, opcoes: list[str]) -> str:
    """Mostra as opções numeradas; Enter mantém a atual."""
    print(f"\n   {texto}")
    for i, opcao in enumerate(opcoes, 1):
        print(f"     {i}) {ROTULOS.get(opcao, opcao)}{'   ← atual' if opcao == atual else ''}")
    while True:
        resposta = input("   Número [Enter mantém]: ").strip()
        if not resposta:
            return atual
        if resposta.isdigit() and 1 <= int(resposta) <= len(opcoes):
            return opcoes[int(resposta) - 1]
        print("   Opção inválida.")


def _escolher(nome: str) -> str:
    return _perguntar(TITULOS[nome], pref(nome), OPCOES[nome])


def _ordem_valida(numeros: list[str], quantidade: int) -> bool:
    """Pelo menos um número, todos entre 1 e `quantidade`, sem repetir."""
    no_intervalo = all(n.isdigit() and 1 <= int(n) <= quantidade for n in numeros)
    return bool(numeros) and no_intervalo and len(set(numeros)) == len(numeros)


def _ordem_ias() -> str:
    """Pergunta a ordem da linha de IAs (ex.: "2 1 3"); as que não forem digitadas ficam de fora."""
    nomes = list(IAS)
    print("\n   Linha de IAs: digite os números na ordem em que devem ser tentadas.")
    print("   A primeira responde; as outras só entram se a anterior falhar.")
    for i, nome in enumerate(nomes, 1):
        print(f"     {i}) {IAS[nome]}")
    atual = " ".join(str(nomes.index(nome) + 1) for nome in lista("BOT_IAS") if nome in nomes)
    while True:
        numeros = (input(f"   Ordem [{atual}]: ").strip() or atual).replace(",", " ").split()
        if _ordem_valida(numeros, len(nomes)):
            return ",".join(nomes[int(n) - 1] for n in numeros)
        print("   Use números de 1 a 3, sem repetir (ex.: 1 3).")


def _pedir(chave: Chave) -> "str | None":
    """Pede um valor do .env; None se a pessoa só apertou Enter (mantém o atual ou pula)."""
    atual = os.getenv(chave.nome) or chave.padrao
    if chave.ajuda:
        print(f"     ({chave.ajuda})")
    situacao = "já configurado, Enter mantém" if atual else "Enter pula"
    if atual and not chave.segredo:
        situacao = f"{atual}, Enter mantém"
    perguntar = getpass.getpass if chave.segredo else input
    valor = perguntar(f"   {chave.rotulo} [{situacao}]: ").strip()
    if valor:
        return valor
    return chave.padrao if chave.padrao and not os.getenv(chave.nome) else None


def _chaves_necessarias(escolhas: dict[str, str]) -> list[Chave]:
    """As chaves que as escolhas precisam: das IAs da linha, do Moodle pela API e do Instagram."""
    grupos = escolhas["BOT_IAS"].split(",")
    plataformas = escolhas["BOT_PLATAFORMAS"].split(",")
    if "moodle" in plataformas and "api" in escolhas["BOT_MOODLE_MODOS"].split(","):
        grupos.append("moodle:api")
    if "instagram" in plataformas:
        grupos += ["instagram"] + [f"instagram:{m}" for m in escolhas["BOT_IG_LOGIN"].split(",")]
    return [chave for grupo in grupos for chave in CHAVES.get(grupo, [])]


def _pedir_chaves(escolhas: dict[str, str]) -> dict[str, str]:
    chaves = _chaves_necessarias(escolhas)
    if chaves:
        print("\n   Chaves e contas (o que for segredo não aparece enquanto você digita):")
    respostas = {chave.nome: _pedir(chave) for chave in chaves}
    return {nome: valor for nome, valor in respostas.items() if valor}


def configurar() -> dict[str, str]:
    """Pergunta tudo e devolve os valores novos (escolhas e chaves)."""
    novos = {"BOT_IAS": _ordem_ias()}
    for ia in novos["BOT_IAS"].split(","):
        novos.update({ajuste: _escolher(ajuste) for ajuste in AJUSTES[ia]})
    novos["BOT_PLATAFORMAS"] = _escolher("BOT_PLATAFORMAS")
    plataformas = novos["BOT_PLATAFORMAS"].split(",")
    novos["BOT_MOODLE_MODOS"] = _escolher("BOT_MOODLE_MODOS") if "moodle" in plataformas else pref("BOT_MOODLE_MODOS")
    novos["BOT_IG_LOGIN"] = _escolher("BOT_IG_LOGIN") if "instagram" in plataformas else pref("BOT_IG_LOGIN")
    novos["BOT_VIGIA"] = _escolher("BOT_VIGIA")
    return {**novos, **_pedir_chaves(novos), "BOT_CONFIGURADO": "1"}


# ── salvar ───────────────────────────────────────────────────────────────────

def _no_formato_do_env(valor: str) -> str:
    """Põe aspas quando precisa: sem elas, um "#" ou espaço cortaria o valor (ex.: uma senha)."""
    if not any(c in valor for c in " #'\"\\"):
        return valor
    if "'" not in valor:
        return f"'{valor}'"
    return '"' + valor.replace("\\", "\\\\").replace('"', '\\"') + '"'


def salvar(valores: dict[str, str], arquivo: Path | None = None) -> None:
    """Grava no .env (ou em `arquivo`): troca as linhas que já existem e acrescenta as que faltam."""
    arquivo = arquivo or ENV
    linhas = arquivo.read_text(encoding="utf-8").splitlines() if arquivo.exists() else []
    faltam = {nome: _no_formato_do_env(valor) for nome, valor in valores.items()}
    for i, linha in enumerate(linhas):
        nome = linha.split("=", 1)[0].strip()
        if nome in faltam:
            linhas[i] = f"{nome}={faltam.pop(nome)}"
    linhas += [f"{nome}={valor}" for nome, valor in faltam.items()]
    arquivo.write_text("\n".join(linhas) + "\n", encoding="utf-8")


# ── o menu ───────────────────────────────────────────────────────────────────

def _quer_configurar() -> bool:
    """Primeira vez e --config vão direto para o menu; senão pergunta (Enter usa as salvas)."""
    if primeira_vez():
        print("\n👋 Primeira vez por aqui: vamos configurar o bot.")
        return True
    if "--config" in sys.argv:
        return True
    return input("   [Enter] usar estas · [c] configurar: ").strip().lower() == "c"


def main() -> None:
    """Menu do start: mostra as escolhas e, se pedido, deixa mudar (sem terminal, só mostra)."""
    load_dotenv(ENV)
    print("⚙️  Preferências:\n" + resumo())
    if not sys.stdin.isatty():
        if primeira_vez():
            print("   (sem terminal: rode o start num terminal para configurar; usando o padrão)")
        return
    if not _quer_configurar():
        return
    novos = configurar()
    salvar(novos)
    os.environ.update(novos)
    print("\n✅ Salvo no .env:\n" + resumo())


if __name__ == "__main__":
    main()
