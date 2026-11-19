"""Ponto de entrada (`bot-moodle`): sobe o que foi escolhido no menu do start.

Cada plataforma tem uma sequência de jeitos de conectar (a reserva): o bot sobe o primeiro que
funcionar e, se ele parar (ex.: a chave do Moodle venceu), sobe o próximo.

- Moodle pela API: uma thread lê as conversas pela API oficial (plataformas/moodle.py).
- Moodle pela extensão: um servidor na porta 5000 recebe as mensagens (plataformas/extensao.py).
- Instagram: uma thread lê a DM; o login tenta senha e/ou sessionid (plataformas/instagram.py).
- Vigia ligado: este mesmo programa roda num processo filho, que o vigia reinicia se cair.

Tudo passa pela mesma rota /check_and_save (comandos.py): os comandos e o histórico são os
mesmos em todas as plataformas.
"""

import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from threading import Thread

from dotenv import load_dotenv
from flask import Flask
from flask_cors import CORS

from bot_moodle import caminhos, comandos, db
from bot_moodle.ia import criar_cliente
from bot_moodle.inicio import vigia
from bot_moodle.inicio.preferencias import lista, pref
from bot_moodle.plataformas import extensao, instagram, moodle as moodle_api

# como subir cada jeito de conectar: recebe o app e devolve a thread (None se não deu)
INICIAR_MOODLE: dict[str, Callable] = {"api": moodle_api.iniciar, "extensao": extensao.iniciar}


@dataclass(frozen=True)
class Escolhas:
    """O que sobe, segundo as preferências (BOT_* no .env)."""

    instagram: bool
    moodle: tuple  # os jeitos de conectar no Moodle, na ordem da reserva ("api", "extensao")
    vigia: bool

    @classmethod
    def das_preferencias(cls) -> "Escolhas":
        """As escolhas salvas pelo menu (ou os padrões)."""
        ligadas = lista("BOT_PLATAFORMAS")
        modos = tuple(m for m in lista("BOT_MOODLE_MODOS") if m in INICIAR_MOODLE)
        return cls(instagram="instagram" in ligadas,
                   moodle=modos if "moodle" in ligadas else (),
                   vigia=pref("BOT_VIGIA") == "1")

    @property
    def pode_ter_servidor(self) -> bool:
        """O servidor da extensão pode subir (como jeito principal ou reserva)."""
        return "extensao" in self.moodle


@dataclass
class Plataforma:
    """Uma plataforma e os jeitos de conectar que ainda não foram tentados, na ordem da reserva."""

    nome: str
    jeitos: list[tuple[str, Callable]]
    leitor: Thread | None = None
    atual: str = ""

    def viva(self) -> bool:
        """Tem um leitor de pé agora."""
        return self.leitor is not None and self.leitor.is_alive()

    def acabou(self) -> bool:
        """Parou e não sobrou reserva para tentar."""
        return not self.viva() and not self.jeitos

    def subir(self, app: Flask) -> None:
        """Se o jeito atual não está de pé, tenta os próximos até um subir."""
        while self.jeitos and not self.viva():
            proximo, iniciar = self.jeitos.pop(0)
            if self.atual:
                print(f"🔁 {self.nome}: {self.atual} não está funcionando; tentando {proximo}.")
            self.atual, self.leitor = proximo, iniciar(app)


def plataformas(escolhas: Escolhas) -> list[Plataforma]:
    """As plataformas ligadas, cada uma com a sua sequência de jeitos de conectar."""
    ligadas = [Plataforma("Moodle", [(modo, INICIAR_MOODLE[modo]) for modo in escolhas.moodle])]
    if escolhas.instagram:
        ligadas.append(Plataforma("Instagram", [("login", instagram.iniciar)]))
    return [plataforma for plataforma in ligadas if plataforma.jeitos]


def create_app() -> Flask:
    """O app Flask com a rota dos comandos, o banco e o cliente do Gemini."""
    app = Flask(__name__)
    CORS(app)
    caminhos.DADOS.mkdir(exist_ok=True)
    api_key = os.getenv("API_KEY")
    if not api_key and "gemini" in lista("BOT_IAS"):
        print("\n⚠️ 'API_KEY' não encontrada no .env: o Gemini vai falhar na linha de IAs.\n")
    comandos.init_handlers(db.conectar(os.getenv("DB_FILE", str(caminhos.BANCO))),
                           criar_cliente(api_key))
    app.register_blueprint(comandos.bp)
    app.add_url_rule("/health", "health", lambda: "ok")  # o vigia confere por aqui
    return app


def _manter(app: Flask, ligadas: list[Plataforma]) -> None:
    """Mantém as plataformas de pé (subindo a reserva quando uma para) até todas acabarem."""
    try:
        while not all(plataforma.acabou() for plataforma in ligadas):
            for plataforma in ligadas:
                plataforma.subir(app)
                if plataforma.leitor:
                    plataforma.leitor.join(1)  # com timeout: no Windows um join() sem ele ignora o Ctrl+C
    except KeyboardInterrupt:
        return
    sys.exit(vigia.NAO_REINICIAR)  # nenhum jeito de conectar funcionou: reiniciar repetiria o erro


def main() -> None:
    """Entry point do `bot-moodle` (pyproject.toml)."""
    load_dotenv(caminhos.ENV)
    escolhas = Escolhas.das_preferencias()
    if escolhas.vigia and not os.getenv("BOT_VIGIADO"):
        vigia.rodar(servidor=escolhas.pode_ter_servidor)  # sobe este mesmo main num processo filho
        return
    app = create_app()
    _manter(app, plataformas(escolhas))


if __name__ == "__main__":
    main()
