"""Testes da decisão entre camada de texto e OCR.

Por que estes casos: o INSTRUCOES lista "assumir que todo PDF tem camada de
texto" entre os erros que derrubam entregas, e o conjunto oficial tem um caso
traiçoeiro — `payroll-04` TEM camada de texto, mas ela contém só o rodapé.
Um teste de "tem alguma palavra?" passaria e a transcrição sairia vazia.
"""

from __future__ import annotations

from pathlib import Path

from app.extraction.extracted_page import ExtractionSource
from app.extraction.native_text import extract_native_pages

EXEMPLOS = Path(__file__).resolve().parents[2] / "exemplos"


def test_documento_com_texto_nativo_e_lido_sem_ocr():
    paginas = extract_native_pages(str(EXEMPLOS / "time-card-01.pdf"))

    assert len(paginas) == 5
    primeira = paginas[0]
    assert primeira.source is ExtractionSource.TEXTO_NATIVO
    assert len(primeira.words) > 300

    texto = primeira.text()
    assert "SISTEMA DE PONTO ELETRONICO" in texto
    assert "Mes/Ano" in texto
    assert "Dia Semana Jornada Entrada Saida Ocorrencia Qtde" in texto


def test_titulo_do_sipon_vem_com_letras_espacadas():
    """Achado real, que restringe como o parser pode reconhecer este layout.

    O título é impresso letra a letra: "F O L H A  DE  F R E Q U E N C I A".
    Procurar "FOLHA DE FREQUENCIA" no texto NÃO encontra nada. A impressão
    digital deste layout precisa usar outro trecho — o cabeçalho da tabela, por
    exemplo, que vem com espaçamento normal.
    """
    paginas = extract_native_pages(str(EXEMPLOS / "time-card-01.pdf"))
    texto = paginas[0].text()

    assert "FOLHA DE FREQUENCIA" not in texto
    assert "F O L H A" in texto


def test_paginas_sem_camada_de_texto_saem_vazias_na_extracao_nativa():
    """São essas que o extractor precisa mandar para OCR."""
    paginas = extract_native_pages(str(EXEMPLOS / "time-card-03.pdf"))

    assert len(paginas) == 5
    assert all(pagina.is_empty for pagina in paginas)


def test_camada_de_texto_apenas_de_rodape_fica_abaixo_do_limiar():
    """O caso traiçoeiro do conjunto oficial.

    `payroll-04` devolve ~12 palavras por página — só o carimbo de assinatura.
    O conteúdo do recibo é vetorial. Se o critério fosse "tem alguma palavra?",
    a página iria para o caminho nativo e a transcrição sairia vazia.
    """
    paginas = extract_native_pages(str(EXEMPLOS / "payroll-04.pdf"))

    for pagina in paginas:
        assert 0 < len(pagina.words) < 40


def test_numero_da_pagina_vem_do_indice_real_do_pdf():
    """Nunca do número impresso — `payroll-03` imprime "Pág: 1" em todas."""
    paginas = extract_native_pages(str(EXEMPLOS / "payroll-03.pdf"))

    assert [pagina.page for pagina in paginas] == [1, 2, 3, 4, 5]

    # o documento realmente imprime o mesmo número em páginas diferentes
    assert "Pág: 1" in paginas[0].text()
    assert "Pág: 1" in paginas[1].text()
