"""Parser do holerite `payroll-03` — validado contra o PDF real.

Por que estes casos: a separação `fields` × `bases` é, segundo o próprio
README, "a decisão central" do holerite, e errar "contamina a planilha
inteira". Os testes abaixo atacam justamente as formas de errar essa divisão
neste documento.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.extraction.native_text import extract_native_pages
from app.parsers.payslip.demonstrativo_mensal import DemonstrativoMensalParser

EXEMPLOS = Path(__file__).resolve().parents[2] / "exemplos"


@pytest.fixture(scope="module")
def value():
    paginas = extract_native_pages(str(EXEMPLOS / "payroll-03.pdf"))
    return DemonstrativoMensalParser().parse(paginas)


# ---------------------------------------------------------------- estrutura


def test_todas_as_paginas_aparecem_com_competencia(value):
    """Uma competência por página, e a cadeia atravessa a virada de ano."""
    competencias = [(p["month"], p["year"]) for p in value["pages"]]

    assert competencias == [
        ("10", "2019"),
        ("11", "2019"),
        ("12", "2019"),
        ("01", "2020"),
        ("02", "2020"),
    ]
    assert [p["page"] for p in value["pages"]] == [1, 2, 3, 4, 5]


def test_page_vem_do_indice_real_e_nao_do_impresso(value):
    """O documento imprime `Pág: 1` em TODAS as páginas."""
    assert [p["page"] for p in value["pages"]] == [1, 2, 3, 4, 5]


# ------------------------------------------------------- fields versus bases


def test_nenhuma_base_vaza_para_fields(value):
    """Se `Base INSS` ou `Total` virarem verba, viram coluna e contaminam tudo."""
    labels = {campo["label"] for p in value["pages"] for campo in p["fields"]}

    proibidos = [
        label
        for label in labels
        if any(
            marcador in label.lower()
            for marcador in ("base ", "total", "líqüido", "liquido", "f.g.t.s")
        )
    ]
    assert proibidos == []


def test_bases_trazem_os_totais_e_as_bases_de_calculo(value):
    labels = {base["label"] for base in value["pages"][0]["bases"]}

    assert {
        "Total Proventos",
        "Total Descontos",
        "Líqüido",
        "Base I.N.S.S.",
        "Base I.R.R.F.",
        "Dep. I.R.R.F.",
        "F.G.T.S. do Mês",
        "Base FGTS",
    } <= labels


def test_cabecalho_do_funcionario_nao_vira_base(value):
    """`Salário Base : 1.678,61` usa o MESMO formato das bases.

    A diferença é só a posição — acima da tabela de verbas. Se entrasse, seria
    uma base falsa em toda página.
    """
    labels = {base["label"] for p in value["pages"] for base in p["bases"]}

    assert "Salário Base" not in labels
    assert "Grupo" not in labels
    assert "Centro Custo" not in labels


def test_rodape_de_assinatura_nao_vira_base(value):
    """O rodapé termina em `:` mas não tem valor monetário."""
    labels = {base["label"] for p in value["pages"] for base in p["bases"]}

    assert not any("ssinado" in label for label in labels)
    assert not any("Juntado" in label for label in labels)


# -------------------------------------------------------------- contrato


def test_code_e_reference_usam_string_vazia(value):
    """Especificação: string vazia quando ausente, nunca `null`."""
    for pagina in value["pages"]:
        for campo in pagina["fields"]:
            assert isinstance(campo["code"], str)
            assert isinstance(campo["reference"], str)

    sem_referencia = [
        campo
        for campo in value["pages"][0]["fields"]
        if campo["label"] == "DSR sobre Variaveis"
    ]
    assert sem_referencia[0]["reference"] == ""


def test_dinheiro_permanece_string_no_formato_brasileiro(value):
    campo = value["pages"][0]["fields"][0]

    assert campo["label"] == "Dias Trabalhados"
    assert campo["value"] == "1.678,61"
    assert isinstance(campo["value"], str)


def test_codigos_nao_numericos_sao_preservados(value):
    """Este documento usa códigos como `/314`, `/B02` e `/337`."""
    codigos = {campo["code"] for campo in value["pages"][0]["fields"]}

    assert "/314" in codigos
    assert "/B02" in codigos


def test_valor_vem_de_proventos_ou_de_descontos(value):
    """O valor da verba está numa coluna OU na outra, nunca nas duas."""
    campos = {c["label"]: c["value"] for c in value["pages"][0]["fields"]}

    assert campos["Dias Trabalhados"] == "1.678,61"  # provento
    assert campos["Contr. INSS Remuneração"] == "177,03"  # desconto


# ------------------------------------------------------------ decisões P2


def test_linha_total_vira_duas_bases_identificaveis(value):
    """O documento imprime `Total` uma vez sob duas colunas.

    Duas bases chamadas apenas "Total" seriam ambíguas. O label é composto com
    o título da coluna, que o próprio documento imprime.
    """
    bases = {base["label"]: base["value"] for base in value["pages"][0]["bases"]}

    assert bases["Total Proventos"] == "1.967,07"
    assert bases["Total Descontos"] == "859,46"


def test_base_sem_valor_e_preservada_com_string_vazia(value):
    """`Base I.R.R.F. 13o.:` aparece sem valor em todas as páginas.

    Omitir esconderia que o documento traz o rótulo. Preservar com valor vazio
    é mais fiel e não afeta a planilha, porque bases não viram colunas.
    """
    bases = {base["label"]: base["value"] for base in value["pages"][0]["bases"]}

    assert "Base I.R.R.F. 13o." in bases
    assert bases["Base I.R.R.F. 13o."] == ""


# ------------------------------------------------------------------ detecção


def test_matches_reconhece_o_documento_certo():
    paginas = extract_native_pages(str(EXEMPLOS / "payroll-03.pdf"))
    assert DemonstrativoMensalParser().matches(paginas) == 1.0


def test_matches_recusa_um_cartao_de_ponto():
    paginas = extract_native_pages(str(EXEMPLOS / "time-card-01.pdf"))
    assert DemonstrativoMensalParser().matches(paginas) == 0.0


def test_matches_recusa_outro_holerite():
    """`payroll-01` é ficha financeira, com estrutura completamente diferente."""
    paginas = extract_native_pages(str(EXEMPLOS / "payroll-01.pdf"))
    assert DemonstrativoMensalParser().matches(paginas) == 0.0
