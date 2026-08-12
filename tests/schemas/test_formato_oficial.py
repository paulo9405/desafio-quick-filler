"""Os exemplos LITERAIS do README oficial precisam validar contra os schemas.

Por que este caso: é o teste mais barato que existe contra o risco mais caro do
desafio. O README avisa que divergir do formato "significa nota zero em
precisão, mesmo com a extração perfeita", e a correção é automatizada.

Se alguém renomear um campo, trocar `""` por `null` ou converter dinheiro para
float, este teste quebra antes de a mudança chegar na entrega.

Os dicionários abaixo são cópia literal dos exemplos do README — não editar
para "arrumar" nada.
"""

from __future__ import annotations

from app.schemas.payslip import PayslipValue
from app.schemas.timesheet import TimesheetValue

EXEMPLO_CARTAO_PONTO = {
    "pages": [
        {
            "page": 1,
            "days": [
                {
                    "date_raw": "21/05/2019",
                    "punches": [
                        {"kind": "IN", "time_raw": "08:25", "time_hhmm": "08:25"},
                        {"kind": "OUT", "time_raw": "18:25", "time_hhmm": "18:25"},
                    ],
                },
                {"date_raw": "25/05/2019", "punches": []},
            ],
        }
    ]
}

EXEMPLO_HOLERITE = {
    "pages": [
        {
            "page": 1,
            "year": "2020",
            "month": "01",
            "fields": [
                {
                    "code": "0010",
                    "label": "Salário Base",
                    "reference": "220,00",
                    "value": "2.389,77",
                },
                {
                    "code": "5560",
                    "label": "Horas Extras - 50%",
                    "reference": "8,00",
                    "value": "155,91",
                },
                {
                    "code": "0998",
                    "label": "INSS",
                    "reference": "",
                    "value": "262,87",
                },
            ],
            "bases": [
                {"label": "Base INSS", "value": "2.545,68"},
                {"label": "Total Vencimentos", "value": "2.545,68"},
                {"label": "Valor Líquido", "value": "2.282,81"},
            ],
        }
    ]
}


def test_exemplo_de_cartao_de_ponto_do_readme_valida():
    modelo = TimesheetValue.model_validate(EXEMPLO_CARTAO_PONTO)
    assert modelo.model_dump(mode="json") == EXEMPLO_CARTAO_PONTO


def test_exemplo_de_holerite_do_readme_valida():
    modelo = PayslipValue.model_validate(EXEMPLO_HOLERITE)
    assert modelo.model_dump(mode="json") == EXEMPLO_HOLERITE


def test_incerteza_por_caractere_atravessa_o_schema():
    """`?` no meio de um valor não pode ser rejeitado nem normalizado.

    É a regra mais importante do desafio: nunca inventar um caractere. Se o
    schema exigisse `HH:MM` válido ou número, a solução seria obrigada a chutar
    ou a descartar o registro.
    """
    valor = {
        "pages": [
            {
                "page": 1,
                "days": [
                    {
                        "date_raw": "2?/05/2019",
                        "punches": [
                            {"kind": "IN", "time_raw": "0?:25", "time_hhmm": "0?:25"}
                        ],
                    }
                ],
            }
        ]
    }

    modelo = TimesheetValue.model_validate(valor)
    assert modelo.pages[0].days[0].punches[0].time_hhmm == "0?:25"

    holerite = PayslipValue.model_validate(
        {
            "pages": [
                {
                    "page": 1,
                    "year": "2020",
                    "month": "01",
                    "fields": [
                        {
                            "code": "0010",
                            "label": "Salário Base",
                            "reference": "",
                            "value": "2.3?9,77",
                        }
                    ],
                    "bases": [],
                }
            ]
        }
    )
    assert holerite.pages[0].fields[0].value == "2.3?9,77"


def test_code_e_reference_ausentes_viram_string_vazia():
    """Especificação: string vazia quando não houver — nunca `null`."""
    pagina = PayslipValue.model_validate(
        {
            "pages": [
                {
                    "page": 1,
                    "year": "2019",
                    "month": "09",
                    "fields": [{"label": "SALARIO", "value": "953,36"}],
                    "bases": [],
                }
            ]
        }
    ).pages[0]

    serializado = pagina.model_dump(mode="json")["fields"][0]
    assert serializado["code"] == ""
    assert serializado["reference"] == ""
    assert serializado["code"] is not None
    assert serializado["reference"] is not None
