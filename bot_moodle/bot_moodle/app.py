"""Entry point da aplicação Flask."""

import os
import sys

from dotenv import load_dotenv
from flask import Flask
from flask_cors import CORS

from bot_moodle.core.ai import criar_cliente
from bot_moodle.db import conectar
from bot_moodle import instagram, moodle_api, vigia
from bot_moodle.preferencias import lista, pref
from bot_moodle.routes.chat import bp, init_handlers

load_dotenv()


def create_app() -> Flask:
    """
    Factory da aplicação Flask.
    Separa criação de configuração para facilitar testes.
    """
    app = Flask(__name__)
    CORS(app)

    api_key = os.getenv("API_KEY")
    if not api_key and "gemini" in lista("BOT_IAS"):
        print("\n⚠️ 'API_KEY' não encontrada no .env: o Gemini vai falhar na linha de IAs.\n")

    db_conn = conectar(os.getenv("DB_FILE", "moodle_history.duckdb"))
    ai_client = criar_cliente(api_key)

    init_handlers(db_conn, ai_client)
    app.register_blueprint(bp)
    app.add_url_rule("/health", "health", lambda: "ok")  # o vigia confere por aqui

    return app


def main() -> None:
    """Entry point para `bot-moodle` no pyproject.toml."""
    plataformas = lista("BOT_PLATAFORMAS")
    moodle_api_ligado = "moodle" in plataformas and pref("BOT_MOODLE_MODO") == "api"
    servidor = "moodle" in plataformas and not moodle_api_ligado  # a extensão fala pela porta
    if pref("BOT_VIGIA") == "1" and not os.getenv("BOT_VIGIADO"):
        vigia.rodar(servidor=servidor)  # sobe este mesmo main num processo filho
        return

    app = create_app()
    threads = [t for t in (
        instagram.iniciar(app) if "instagram" in plataformas else None,
        moodle_api.iniciar(app) if moodle_api_ligado else None,
    ) if t]
    if servidor:
        port = int(os.getenv("PORT", "5000"))
        print(f"Servidor v5 ativo na porta {port}.")
        app.run(port=port, threaded=True)
        return
    # sem servidor: vive enquanto alguma plataforma estiver lendo mensagens
    try:
        while any(t.is_alive() for t in threads):
            for t in threads:
                t.join(1)  # com timeout: no Windows um join() sem ele ignora o Ctrl+C
    except KeyboardInterrupt:
        return
    sys.exit(vigia.NAO_REINICIAR)  # login/chave falhou: reiniciar só repetiria o erro


if __name__ == "__main__":
    main()
