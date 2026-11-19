"""As IAs do bot: a linha de reserva (linha.py), cada IA (claude_cli, claude_api, gemini) e o
testador de código C que elas usam (testador.py)."""

from bot_moodle.ia.gemini import criar_cliente
from bot_moodle.ia.linha import PROVEDORES, chamar, pedir_a_ia

__all__ = ["PROVEDORES", "chamar", "criar_cliente", "pedir_a_ia"]
