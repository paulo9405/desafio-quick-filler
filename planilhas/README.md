# Planilhas geradas dos PDFs de `exemplos/`

Entregável nº 5 da lista oficial: as planilhas produzidas a partir dos oito PDFs
de exemplo do desafio.

Tudo aqui saiu do **fluxo real da aplicação** — `POST /api/transcricoes`,
polling do status, `GET /api/transcricoes/{id}/planilha?formato=...` — rodando
em `docker compose up`. Nenhum arquivo foi produzido por script paralelo
chamando parser ou `export_service` diretamente.

## Os três formatos

Cada documento reconhecido tem `.xlsx`, `.csv` e `.json`. Os três vêm do mesmo
endpoint e do mesmo `value` persistido; o INSTRUCOES lista "implementar só o
`xlsx` no download" entre os erros comuns, então os três estão aqui.

| Formato | O que carrega |
|---|---|
| `.xlsx` | A planilha propriamente dita: cabeçalho `#173772` e os destaques de revisão. |
| `.csv` | As mesmas colunas, `;` e `utf-8-sig` (Excel pt-BR). Sem formatação — CSV não suporta. |
| `.json` | A transcrição como está persistida. **É o único que preserva o par `_raw` / normalizado**, e portanto os `?` de incerteza que vivem só no `_raw`. |

## Resultado por documento

| PDF | Tipo | Status | Tempo | Planilha |
|---|---|---|---|---|
| time-card-01 | cartão de ponto | concluído | 2,3 s | 153 linhas × 5 col |
| time-card-02 | cartão de ponto | concluído | 19,1 s | 153 linhas × 5 col |
| time-card-03 | cartão de ponto | concluído | 27,9 s | 280 linhas × 5 col |
| time-card-04 | cartão de ponto | **erro** | 4,5 s | — não produz planilha |
| payroll-01 | holerite | concluído | 2,3 s | 30 linhas × 55 col |
| payroll-02 | holerite | concluído | 2,3 s | 10 linhas × 39 col |
| payroll-03 | holerite | concluído | 2,2 s | 5 linhas × 14 col |
| payroll-04 | holerite | concluído | 12,8 s | 5 linhas × 17 col |

Tempos medidos localmente (não na EC2), do `POST` até o status sair de
`processando`. Os documentos rápidos usam camada de texto nativa; os lentos
passam por OCR.

## time-card-04 não tem planilha, e isso é o comportamento correto

Nenhum parser reconhece o layout. A transcrição termina em
`status: "erro"` com a mensagem:

> Não foi possível reconhecer o layout deste documento.

E o download é recusado com **HTTP 409**, não com uma planilha vazia. É o
único dos oito que é scan real de papel, com o mês manuscrito. A alternativa —
devolver uma planilha com linhas inventadas ou em branco — violaria a regra
central do domínio. A ausência do arquivo aqui é deliberada.

## Destaques presentes nas planilhas

O destaque marca a linha que precisa de olho humano. Amarelo `#FFF3CD` para
batidas ímpares, página vazia ou `?` na linha; vermelho `#F8D7DA` com borda
`#DC3545` para data ou mês não sequencial.

| Planilha | Amarelas | Vermelhas | Por quê |
|---|---|---|---|
| time-card-01 | 1 | 0 | 29/10/2012 tem uma única batida — número ímpar. |
| time-card-02 | 0 | 0 | — |
| time-card-03 | 4 | 0 | 4 batidas com `?` no `time_raw`. |
| payroll-01 | 0 | 6 | Competência repetida (blocos de acerto/13º). |
| payroll-02 | 0 | 5 | Duas competências iguais por página (blocos MÊS/ACERTO). |
| payroll-03 | 0 | 0 | 10/2019 → 02/2020, sequência limpa (inclusive dez → jan). |
| payroll-04 | 0 | 3 | **Anos lidos errado pelo OCR** — ver abaixo. |

### O caso do payroll-04

As competências lidas foram `09/2019, 10/2016, 11/2016, 09/2016, 01/2020` num
documento de 2019/2020. Os anos `2016` são erro de OCR, e é uma limitação
conhecida e documentada (`SOLUCAO.md`).

O ponto é que **o erro não passa despercebido**: as três linhas saem marcadas em
vermelho na planilha, porque a sequência de competência quebra. O sistema não
consegue ler o ano corretamente, mas consegue dizer que não confia nele — que é
exatamente o que se pede quando "um número errado nunca passa despercebido".

### Os `?` do time-card-03

Nas 4 batidas marcadas, o `?` está no `time_raw` (`"23:00?"`), não no
`time_hhmm` (`"23:00"`). O caractere ilegível é o sufixo `d`/`c` de virada de
dia — os dígitos do horário foram lidos com confiança. Por isso o `.json` é o
formato que preserva a evidência completa: no `.xlsx` e no `.csv` aparece o
horário interpretado, e o que sinaliza a incerteza é o destaque amarelo da linha.

## Conferência

Os números de conteúdo destas planilhas batem com os registrados em
`SOLUCAO.md` — 5 páginas / 153 dias / 369 batidas em time-card-01, 455 verbas e
229 bases em payroll-01, e assim por diante. A verificação foi feita relendo os
arquivos gerados, não a memória do processo.

## Sobre versionar estes arquivos

Estes arquivos são entregáveis e ficam versionados. O conteúdo deles vem dos
PDFs de `exemplos/`, que já são versionados no repositório — não há exposição
nova. O que **nunca** é versionado é `data/`, onde ficam os PDFs enviados por
usuários e o banco.
