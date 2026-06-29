"""Entry point da aplicação Flask."""

import os
from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv

from bot_moodle.core.ai import criar_cliente
from bot_moodle.db import conectar
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
    if not api_key:
        print("\n❌ [ERRO CRÍTICO]: Chave 'API_KEY' não encontrada no .env!\n")

    db_conn   = conectar(os.getenv("DB_FILE", "moodle_history.duckdb"))
    ai_client = criar_cliente(api_key or "")

    init_handlers(db_conn, ai_client)
    app.register_blueprint(bp)

    return app


def main() -> None:
    """Entry point para `bot-moodle` no pyproject.toml."""
    port = int(os.getenv("PORT", "5000"))
    print(f"Servidor v5 ativo na porta {port}.")
    create_app().run(port=port, threaded=True)


if __name__ == "__main__":
    main()
