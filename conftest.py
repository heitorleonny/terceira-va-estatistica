"""
conftest.py — garante que a raiz do projeto esteja no sys.path para os testes.

Com este arquivo na raiz, o pytest consegue importar os módulos do projeto
(db, cards, stats_empirical, historico_precos) a partir de tests/.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
