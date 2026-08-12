"""Testes do registry de parsers.

Por que estes casos: o registry é o ponto de extensão da aplicação — é ele que
será tocado na sessão técnica ao vivo. E o caminho de "nenhum parser reconhece"
precisa ser honesto, não silencioso.
"""

from __future__ import annotations

from pathlib import Path

from app.extraction.native_text import extract_native_pages
from app.parsers.registry import ParserRegistry

EXEMPLOS = Path(__file__).resolve().parents[2] / "exemplos"


def test_registry_escolhe_o_parser_do_layout():
    paginas = extract_native_pages(str(EXEMPLOS / "time-card-01.pdf"))

    parser = ParserRegistry().select("cartao-ponto", paginas)

    assert parser is not None
    assert parser.nome == "sipon"


def test_registry_devolve_none_para_layout_desconhecido():
    """Documento real, de um layout ainda não implementado.

    Devolver `None` é o que faz o pipeline responder "não sei ler este
    documento" em vez de devolver lixo.
    """
    paginas = extract_native_pages(str(EXEMPLOS / "payroll-01.pdf"))

    assert ParserRegistry().select("holerite", paginas) is None


def test_registry_nao_mistura_tipos():
    """Um parser de cartão de ponto nunca é oferecido para um holerite."""
    paginas = extract_native_pages(str(EXEMPLOS / "time-card-01.pdf"))

    assert ParserRegistry().select("holerite", paginas) is None


def test_registry_ignora_parsers_com_score_zero():
    paginas = extract_native_pages(str(EXEMPLOS / "payroll-03.pdf"))

    assert ParserRegistry().select("cartao-ponto", paginas) is None
