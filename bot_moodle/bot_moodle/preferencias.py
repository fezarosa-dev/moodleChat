"""Preferências do bot (IAs, modelos, plataformas, vigia), salvas no .env como BOT_*.

`python -m bot_moodle.preferencias [--config]` é o menu do start: mostra as escolhas e,
se pedido, deixa mudar.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

IAS = {"claude_cli": "Claude Code (CLI)", "claude_api": "Claude API", "gemini": "Gemini"}
PLATAFORMAS = {"moodle": "Moodle", "instagram": "Instagram"}
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
    "BOT_IAS": "claude_cli,gemini",  # linha de reserva, na ordem
    "BOT_CLI_MODELO": "opus",
    "BOT_CLI_EFFORT": "medium",
    "BOT_API_MODELO": "claude-sonnet-5-5",
    "BOT_API_EFFORT": "medium",
    "BOT_GEMINI_MODELO": "gemini-3.5-flash",
    "BOT_PLATAFORMAS": "moodle,instagram",
    "BOT_MOODLE_MODO": "api",  # api (token, sem extensão) ou extensao
    "BOT_VIGIA": "1",
}
OPCOES = {
    "BOT_CLI_MODELO": ["opus", "sonnet", "haiku"],
    "BOT_CLI_EFFORT": EFFORTS,
    "BOT_API_MODELO": ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"],
    "BOT_API_EFFORT": EFFORTS,
    "BOT_GEMINI_MODELO": MODELOS_GEMINI,
    "BOT_PLATAFORMAS": ["moodle,instagram", "moodle", "instagram"],
    "BOT_MOODLE_MODO": ["api", "extensao"],
    "BOT_VIGIA": ["1", "0"],
}
ROTULOS = {"moodle,instagram": "Moodle + Instagram", "moodle": "Só Moodle",
           "instagram": "Só Instagram", "1": "Sim", "0": "Não",
           "api": "Pela API, com a chave MOODLE_TOKEN (sem extensão)",
           "extensao": "Pela extensão do navegador (servidor na porta 5000)"}
# o que cada IA deixa escolher no menu
AJUSTES = {
    "claude_cli": ["BOT_CLI_MODELO", "BOT_CLI_EFFORT"],
    "claude_api": ["BOT_API_MODELO", "BOT_API_EFFORT"],
    "gemini": ["BOT_GEMINI_MODELO"],
}
ENV = Path(".env")


def pref(nome: str) -> str:
    """Valor da preferência (do .env/ambiente), ou o padrão."""
    return os.getenv(nome) or PADROES[nome]


def lista(nome: str) -> list[str]:
    """Preferência em lista (ex.: BOT_IAS="claude_cli,gemini")."""
    return [x for x in pref(nome).split(",") if x]


def resumo() -> str:
    """Escolhas atuais, em texto para o menu."""
    ias = " → ".join(f"{IAS[i]} ({', '.join(pref(a) for a in AJUSTES[i])})"
                     for i in lista("BOT_IAS") if i in IAS)
    modo = {"api": "API", "extensao": "extensão"}.get(pref("BOT_MOODLE_MODO"), "?")
    plats = " + ".join(PLATAFORMAS[p] + (f" ({modo})" if p == "moodle" else "")
                       for p in lista("BOT_PLATAFORMAS") if p in PLATAFORMAS)
    vigia = "ligado" if pref("BOT_VIGIA") == "1" else "desligado"
    return (f"   IAs (na ordem de reserva): {ias or 'nenhuma'}\n"
            f"   Plataformas: {plats}\n"
            f"   Reinício automático se cair ou travar: {vigia}")


def _perguntar(texto: str, atual: str, opcoes: list[str]) -> str:
    """Mostra as opções numeradas; Enter mantém a atual."""
    print(f"\n   {texto}")
    for i, op in enumerate(opcoes, 1):
        print(f"     {i}) {ROTULOS.get(op, op)}{'   ← atual' if op == atual else ''}")
    while True:
        r = input("   Número [Enter mantém]: ").strip()
        if not r:
            return atual
        if r.isdigit() and 1 <= int(r) <= len(opcoes):
            return opcoes[int(r) - 1]
        print("   Opção inválida.")


def _ordem_ias() -> str:
    nomes = list(IAS)
    print("\n   Linha de IAs: digite os números na ordem em que devem ser tentadas.")
    print("   A primeira responde; as outras só entram se a anterior falhar.")
    for i, n in enumerate(nomes, 1):
        print(f"     {i}) {IAS[n]}")
    atual = " ".join(str(nomes.index(n) + 1) for n in lista("BOT_IAS") if n in nomes)
    while True:
        r = input(f"   Ordem [{atual}]: ").strip() or atual
        nums = r.replace(",", " ").split()
        if nums and all(n.isdigit() and 1 <= int(n) <= len(nomes) for n in nums) \
                and len(set(nums)) == len(nums):
            return ",".join(nomes[int(n) - 1] for n in nums)
        print("   Use números de 1 a 3, sem repetir (ex.: 1 3).")


def configurar() -> dict[str, str]:
    """Pergunta tudo e devolve os valores novos."""
    novos = {"BOT_IAS": _ordem_ias()}
    titulos = {"BOT_CLI_MODELO": "Claude Code: modelo", "BOT_CLI_EFFORT": "Claude Code: effort",
               "BOT_API_MODELO": "Claude API: modelo", "BOT_API_EFFORT": "Claude API: effort",
               "BOT_GEMINI_MODELO": "Gemini: modelo inicial"}
    for ia in novos["BOT_IAS"].split(","):
        for nome in AJUSTES[ia]:
            novos[nome] = _perguntar(titulos[nome], pref(nome), OPCOES[nome])
    novos["BOT_PLATAFORMAS"] = _perguntar(
        "Onde o bot funciona", pref("BOT_PLATAFORMAS"), OPCOES["BOT_PLATAFORMAS"])
    if "moodle" in novos["BOT_PLATAFORMAS"]:
        novos["BOT_MOODLE_MODO"] = _perguntar(
            "Como o bot fala com o Moodle", pref("BOT_MOODLE_MODO"), OPCOES["BOT_MOODLE_MODO"])
    novos["BOT_VIGIA"] = _perguntar(
        "Reiniciar sozinho se cair ou travar", pref("BOT_VIGIA"), OPCOES["BOT_VIGIA"])
    return novos


def salvar(valores: dict[str, str], arquivo: Path = ENV) -> None:
    """Grava no .env: troca as linhas que já existem e acrescenta as que faltam."""
    linhas = arquivo.read_text(encoding="utf-8").splitlines() if arquivo.exists() else []
    faltam = dict(valores)
    for i, linha in enumerate(linhas):
        chave = linha.split("=", 1)[0].strip()
        if chave in faltam:
            linhas[i] = f"{chave}={faltam.pop(chave)}"
    linhas += [f"{k}={v}" for k, v in faltam.items()]
    arquivo.write_text("\n".join(linhas) + "\n", encoding="utf-8")


def main() -> None:
    """Menu do start: Enter usa as escolhas salvas; `c` (ou --config) muda."""
    load_dotenv()
    print("⚙️  Preferências:\n" + resumo())
    if not sys.stdin.isatty():
        return
    if "--config" not in sys.argv:
        if input("   [Enter] usar estas · [c] configurar: ").strip().lower() != "c":
            return
    novos = configurar()
    salvar(novos)
    os.environ.update(novos)
    print("\n✅ Salvo no .env:\n" + resumo())


if __name__ == "__main__":
    main()
