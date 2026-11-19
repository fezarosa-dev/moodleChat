"""Onde ficam os arquivos do usuário. Nenhum deles vai para o git (.gitignore).

Os caminhos são relativos à raiz do projeto: o start.sh / start.bat roda o bot de lá.
"""

from pathlib import Path

ENV = Path(".env")                                    # chaves, senhas e as escolhas do menu
DADOS = Path("dados")                                 # tudo que o bot cria sozinho
BANCO = DADOS / "moodle_history.duckdb"               # histórico das conversas (DB_FILE muda)
SESSAO_INSTAGRAM = DADOS / "ig_session.json"          # login do Instagram salvo
VIDA_INSTAGRAM = DADOS / ".instagram_vivo"            # o vigia confere se a DM está sendo lida
VIDA_MOODLE = DADOS / ".moodle_vivo"                  # idem, para o Moodle pela API
