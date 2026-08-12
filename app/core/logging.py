"""Configuração de logging.

Regra do desafio: **sem PII nos logs**. Os PDFs contêm nome, CPF, matrícula,
salário e jornada de pessoas reais.

Na prática isso significa, em todo o projeto:

- nunca logar o conteúdo extraído do documento (texto, linhas, valores);
- nunca logar o nome original do arquivo enviado — ele costuma conter o nome
  da pessoa (ex.: "holerite-joao-silva.pdf");
- identificar o trabalho pelo `id` da transcrição, que é opaco.

O que é seguro logar: id, tipo, status, contagem de páginas, duração, e o tipo
do erro.
"""

from __future__ import annotations

import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    """Configura o logging raiz. Idempotente."""
    root = logging.getLogger()
    if root.handlers:
        root.setLevel(level)
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)s %(name)s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    root.addHandler(handler)
    root.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
