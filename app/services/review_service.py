"""Projeção da transcrição para a interface de revisão.

O README exige que a tabela editável siga "as colunas da planilha do tipo
correspondente", com os problemas destacados "nas mesmas cores da planilha".

Ou seja: tabela e planilha precisam ser a MESMA coisa. Este módulo não
recalcula colunas nem avisos — ele reúne o que `export_service.montar_tabela`
e `warnings_service.avaliar` já produzem, e acrescenta o caminho de cada célula
dentro do `value`.

POR QUE O CAMINHO DA CÉLULA

A planilha é uma projeção do JSON: a coluna `Entrada 2` do dia 5 corresponde a
`pages.0.days.4.punches.2.time_hhmm`. Quando a pessoa corrige aquela célula, a
correção precisa voltar para o lugar certo do JSON, que é o que o PUT
substitui.

Mandar o caminho pronto do backend evita que o JavaScript precise conhecer a
estrutura de cartão de ponto e de holerite — ou seja, evita duplicar regra de
negócio no frontend. O JS só aplica `caminho -> valor` num objeto, o que é
genérico.
"""

from __future__ import annotations

from typing import Any, Dict, List

from app.services.export_service import montar_tabela


def montar_revisao(tipo: str, value: Dict[str, Any]) -> Dict[str, Any]:
    """Monta a tabela de revisão com avisos e caminhos de edição."""
    tabela = montar_tabela(tipo, value)

    linhas: List[Dict[str, Any]] = []
    for indice, celulas in enumerate(tabela.rows):
        avaliacao = tabela.avaliacoes[indice]
        caminhos = tabela.caminhos[indice] if indice < len(tabela.caminhos) else []

        linhas.append(
            {
                "celulas": [
                    {
                        "valor": valor,
                        # String vazia = célula não editável: não existe campo
                        # correspondente no JSON (verba ausente naquela página,
                        # par de batidas que o dia não tem).
                        "caminho": caminhos[coluna] if coluna < len(caminhos) else "",
                    }
                    for coluna, valor in enumerate(celulas)
                ],
                "severidade": (
                    avaliacao.severidade.value if avaliacao.severidade else None
                ),
                "motivos": avaliacao.motivos,
            }
        )

    return {"tipo": tipo, "colunas": tabela.header, "linhas": linhas}
