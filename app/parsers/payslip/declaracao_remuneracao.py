"""Parser do holerite "Declaração Remuneração" — `payroll-02`. Texto nativo.

LAYOUT

    Mês/Ano: 08/2018        Folha de Pagamento: MÊS
    Verba   Nome                    Base / Saldo / Benefício    Valor
     010    VENCIMENTO PADRAO-VP                                3.059,94
     803    PREVI PESSOAL PB2               6.188,63             -433,20
    Remuneração Função Vl. Ref.: 5.017,04  Proventos Retidos: 0,00  ...

    Mês/Ano: 08/2018        Folha de Pagamento: ACERTO
    Verba   Nome                    Base / Saldo / Benefício    Valor
     058    HORA EXTRA-BCO HORAS-CONV       JULHO/18              -12,89

PARTICULARIDADES

1. DOIS BLOCOS por página, com a MESMA competência e folhas diferentes
   (`MÊS` e `ACERTO`). Cada bloco vira uma entrada, e as duas compartilham o
   mesmo `page` — mesmo precedente que o README descreve para a ficha
   financeira. Ver decisão em docs/PROCESSO.md.

2. Descontos vêm com sinal negativo impresso (`-433,20`). O sinal é preservado
   como está: guardamos o que o documento mostra.

3. `reference` é textual com frequência (`JULHO/18`, `AC.SIST/0718`) — é a
   coluna "Base / Saldo / Benefício", que nem sempre traz número.

POR QUE ESTE PARSER NÃO USA FAIXA DE COLUNA PARA TUDO

Medido no documento: os títulos do cabeçalho são centralizados sobre colunas
largas, enquanto os dados são alinhados de outra forma. A faixa derivada de
`Verba`/`Nome` cai NO MEIO do nome da verba — `010 VENCIMENTO` fica inteiro de
um lado e `PADRAO-VP` do outro.

Usar faixa aqui produziria label cortado, e label vira coluna de planilha.
A leitura por token é mais fiel neste layout: o código é o primeiro token, o
valor é o último token monetário, e o que sobra no meio é o nome da verba.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from app.extraction.columns import detect_columns, normalizar
from app.extraction.extracted_page import ExtractedPage, Line
from app.parsers.base import LayoutParser
from app.parsers.uncertainty import ler_valor_monetario

PADRAO_VALOR = re.compile(r"^-?\d{1,3}(?:\.\d{3})*,\d{2}$")
PADRAO_CODIGO = re.compile(r"^\d{3}$")
PADRAO_COMPETENCIA = re.compile(r"(\d{2})\s*/\s*(\d{4})")

MARCADOR_DE_BLOCO = "mes/ano"
TITULO = "declaracao remuneracao"
CABECALHO = ("verba", "nome", "valor")


class DeclaracaoRemuneracaoParser(LayoutParser):
    tipo = "holerite"
    nome = "declaracao_remuneracao"

    # ------------------------------------------------------------- detecção

    def matches(self, pages: List[ExtractedPage]) -> float:
        if not pages:
            return 0.0

        tem_cabecalho = any(
            all(titulo in normalizar(linha.text) for titulo in CABECALHO)
            for pagina in pages
            for linha in pagina.lines()
        )
        if not tem_cabecalho:
            return 0.0

        titulo = any(TITULO in normalizar(pagina.text()) for pagina in pages)
        return 1.0 if titulo else 0.7

    # ---------------------------------------------------------------- parse

    def parse(self, pages: List[ExtractedPage]) -> Dict[str, Any]:
        saida: List[Dict[str, Any]] = []
        for pagina in pages:
            saida.extend(self._parse_page(pagina))
        return {"pages": saida}

    def _parse_page(self, page: ExtractedPage) -> List[Dict[str, Any]]:
        blocos = self._dividir_em_blocos(page.lines())
        faixa = self._faixa_de_referencia(page)

        if not blocos:
            return [
                {
                    "page": page.page, "year": "", "month": "",
                    "fields": [], "bases": [],
                }
            ]

        return [
            {
                "page": page.page,  # as entradas do mesmo PDF compartilham a página
                "year": ano,
                "month": mes,
                "fields": self._ler_verbas(linhas, faixa),
                "bases": self._ler_bases(linhas),
            }
            for linhas, mes, ano in blocos
        ]

    @staticmethod
    def _faixa_de_referencia(page: ExtractedPage) -> Optional[Tuple[float, float]]:
        """Faixa horizontal da coluna `Base / Saldo / Benefício`.

        Sai do cabeçalho da tabela, não de um número fixo.
        """
        layout = detect_columns(page, ("Verba", "Nome", "Base", "Valor"))
        if layout is None:
            return None
        coluna = layout.column("Base")
        return (coluna.x0, coluna.x1) if coluna else None

    def _dividir_em_blocos(
        self, linhas: List[Line]
    ) -> List[Tuple[List[Line], str, str]]:
        """Quebra a página nos blocos que começam em `Mês/Ano:`."""
        inicios = [
            indice
            for indice, linha in enumerate(linhas)
            if MARCADOR_DE_BLOCO in normalizar(linha.text)
        ]

        blocos: List[Tuple[List[Line], str, str]] = []
        for posicao, inicio in enumerate(inicios):
            fim = inicios[posicao + 1] if posicao + 1 < len(inicios) else len(linhas)
            mes, ano = self._ler_competencia(linhas[inicio])
            blocos.append((linhas[inicio + 1 : fim], mes, ano))

        return blocos

    # -------------------------------------------------------------- verbas

    def _ler_verbas(
        self, linhas: List[Line], faixa_referencia: Optional[Tuple[float, float]]
    ) -> List[Dict[str, str]]:
        verbas: List[Dict[str, str]] = []

        for linha in linhas:
            palavras = [w.text for w in linha.words]
            if not palavras or not PADRAO_CODIGO.match(palavras[0]):
                continue

            monetarios = [
                indice
                for indice, texto in enumerate(palavras)
                if PADRAO_VALOR.match(texto)
            ]
            if not monetarios:
                continue

            # O valor da verba é sempre o último monetário da linha; quando há
            # dois, o primeiro é a base/saldo da coluna anterior.
            indice_valor = monetarios[-1]
            indice_referencia = monetarios[-2] if len(monetarios) >= 2 else None

            fim_do_label = (
                indice_referencia if indice_referencia is not None else indice_valor
            )
            miolo = palavras[1:fim_do_label]

            referencia = ""
            if indice_referencia is not None:
                referencia = palavras[indice_referencia]
            elif miolo and self._na_faixa_de_referencia(
                linha, fim_do_label - 1, faixa_referencia
            ):
                # Referência textual (`JULHO/18`, `AC.SIST/0718`) fica na coluna
                # "Base / Saldo / Benefício", à direita do nome da verba.
                referencia = miolo[-1]
                miolo = miolo[:-1]

            label = " ".join(miolo).strip()
            if not label:
                continue

            leitura = ler_valor_monetario(palavras[indice_valor])
            verbas.append(
                {
                    "code": palavras[0],
                    "label": label,
                    "reference": referencia,
                    "value": leitura.raw if leitura else palavras[indice_valor],
                }
            )

        return verbas

    @staticmethod
    def _na_faixa_de_referencia(
        linha: Line, indice: int, faixa: Optional[Tuple[float, float]]
    ) -> bool:
        """O último token antes do valor está na coluna de referência?

        A distinção é POSICIONAL, e não textual. A primeira versão deste parser
        tentava adivinhar pelo conteúdo — supunha que uma referência conteria
        `/`, como `JULHO/18`. Isso descartou a verba
        `192 ATFC-AD.TEMP.FATORES/COMI`, cujo NOME também tem barra: o nome
        virou referência, o label ficou vazio e a linha sumiu da saída.

        A coluna resolve o caso sem adivinhação.
        """
        if faixa is None or indice < 0 or indice >= len(linha.words):
            return False
        inicio, fim = faixa
        return inicio <= linha.words[indice].center_x < fim

    # --------------------------------------------------------------- bases

    def _ler_bases(self, linhas: List[Line]) -> List[Dict[str, str]]:
        """Lê os pares `Rótulo: valor`, três por linha, abaixo das verbas."""
        bases: List[Dict[str, str]] = []

        for linha in linhas:
            palavras = [w.text for w in linha.words]
            if palavras and PADRAO_CODIGO.match(palavras[0]):
                continue  # linha de verba
            bases.extend(self._ler_pares(palavras))

        return bases

    def _ler_pares(self, palavras: List[str]) -> List[Dict[str, str]]:
        encontrados: List[Dict[str, str]] = []
        rotulo: List[str] = []
        indice = 0

        while indice < len(palavras):
            texto = palavras[indice]

            if texto.endswith(":"):
                rotulo.append(texto[:-1])
                nome = " ".join(rotulo).strip()
                rotulo = []
                indice += 1

                valor = ""
                if indice < len(palavras) and PADRAO_VALOR.match(palavras[indice]):
                    leitura = ler_valor_monetario(palavras[indice])
                    valor = leitura.raw if leitura else palavras[indice]
                    indice += 1

                if nome:
                    encontrados.append({"label": nome, "value": valor})
                continue

            rotulo.append(texto)
            indice += 1

        # Linha sem nenhum valor monetário não é seção de bases — descarta o
        # rodapé de assinatura, que também termina em `:`.
        if not any(par["value"] for par in encontrados):
            return []

        return encontrados

    # --------------------------------------------------------- competência

    @staticmethod
    def _ler_competencia(linha: Line) -> Tuple[str, str]:
        casado = PADRAO_COMPETENCIA.search(linha.text)
        if not casado:
            return "", ""
        mes, ano = casado.group(1), casado.group(2)
        return (mes, ano) if 1 <= int(mes) <= 12 else ("", "")
