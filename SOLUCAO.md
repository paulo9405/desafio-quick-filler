# SOLUCAO.md

Como o sistema funciona e por que foi construído assim.

O histórico do desenvolvimento — decisões tomadas no caminho, erros, medições e
uso de IA — está em [`PROCESSO.md`](PROCESSO.md). Este documento
descreve o **resultado**.

---

## Visão geral

Transcreve cartões de ponto e holerites em PDF para dados estruturados e
planilhas, com revisão humana no meio do caminho.

```
enviar PDF → processar → revisar/corrigir → baixar planilha
```

**Publicado em:** https://quickfiller.paulodev.net

**Cobertura:** 7 dos 8 documentos oficiais. O oitavo falha de forma explícita —
ver [Limitações](#limitações).

| Documento | Extração | Resultado |
|---|---|---|
| `time-card-01` | texto nativo | 5 pág · 153 dias · 369 batidas |
| `time-card-02` | OCR | 5 pág · 153 dias · 372 batidas |
| `time-card-03` | OCR | 5 pág · 280 dias · 826 batidas · 4 com `?` |
| `time-card-04` | OCR | **não suportado** |
| `payroll-01` | texto nativo | 30 entradas · 455 verbas · 229 bases |
| `payroll-02` | texto nativo | 10 entradas · 92 verbas · 85 bases |
| `payroll-03` | texto nativo | 5 entradas · 44 verbas · 45 bases |
| `payroll-04` | OCR | 5 entradas · 42 verbas · 40 bases |

As planilhas geradas a partir desses PDFs estão em
[`planilhas/`](planilhas/README.md), nos três formatos, produzidas pelo fluxo
real da aplicação. `time-card-04` não tem planilha, e o motivo está lá.

---

## Como executar

```bash
docker compose up
```

Aplicação em http://localhost:8000. A imagem já traz Tesseract e o idioma
português — não há nada a instalar no host.

Testes:

```bash
docker run --rm -v "$PWD":/srv -w /srv quick-filler-app python -m pytest
```

---

## Arquitetura

```
PDF
 ↓  DocumentService — valida, persiste, agenda
 ↓  Extração: a página tem camada de texto útil?
     ├── sim → pdfplumber (palavras + coordenadas)
     └── não → pypdfium2 (render 300dpi) → Tesseract (palavras + coordenadas + confiança)
 ↓  ExtractedPage[]  ← contrato interno único
 ↓  ParserRegistry → parser do layout
 ↓  value no formato oficial → SQLite
 ↓
 ├── API + interface de revisão (edição → PUT)
 └── WarningsService (funções puras) → exports xlsx/csv/json
```

**Um pipeline, dois extratores.** Upload, processamento, revisão e download são
compartilhados. O que muda é o parser e o formato da planilha.

### `ExtractedPage` — a decisão central

Texto nativo e OCR produzem **a mesma estrutura**: palavras com bounding box e,
quando disponível, confiança. Consequências:

- todo parser funciona nos dois caminhos sem saber qual foi usado;
- a detecção de coluna pelo cabeçalho fica disponível em ambos;
- a confiança viaja com o dado.

Coordenadas do OCR são convertidas de pixels para pontos de PDF, para que os
dois caminhos falem a mesma unidade.

### Registry de parsers

Cada parser expõe `matches(pages) → score` e `parse(pages) → value`. O registry
escolhe o maior score acima de zero, restrito ao `tipo` do upload. Nenhum
reconhece → `status: "erro"` com mensagem legível.

Adicionar um layout é criar um arquivo em `app/parsers/<tipo>/` e registrá-lo.
Nada mais muda.

---

## Tecnologias

| | | Por quê |
|---|---|---|
| FastAPI + Pydantic | API | validação do contrato e OpenAPI |
| **pdfplumber** | texto + coordenadas | `extract_words()` é a base da detecção de coluna |
| **pypdfium2** | render para OCR | rápido, licença permissiva |
| **Tesseract** (`pytesseract`) | OCR | `image_to_data` dá bbox **e confiança** por palavra |
| openpyxl | XLSX | cor de fundo, negrito e borda exigidos |
| SQLite | persistência | um documento JSON por transcrição |
| HTML + Bootstrap + JS puro | interface | sem build step, sem framework |

Alternativa considerada: **PyMuPDF** faria extração e render numa lib só. Foi
dada preferência a bibliotecas com licenças permissivas e adequadas ao contexto
de distribuição do desafio.

---

## Estratégia de extração

**O critério é a presença de camada de texto útil na página**, nunca o nome do
arquivo. A decisão é **por página**: um PDF pode misturar páginas nativas e
digitalizadas.

O limiar (40 palavras) sai de medição nos documentos oficiais:

| Regime | Palavras/página |
|---|---|
| conteúdo real | 158 – 701 |
| `payroll-04` (só rodapé de assinatura) | **12** |
| sem camada de texto | 0 |

`payroll-04` é o caso traiçoeiro: **tem** camada de texto, mas ela contém só o
carimbo de assinatura. Um teste de "tem alguma palavra?" devolveria uma
transcrição vazia.

### OCR

`--psm 6`, 300 dpi, idioma `por`. O modo foi escolhido por medição comparativa:
`psm 3` quebrava as datas e levava o dobro do tempo; `psm 4` recuperava rótulos
num documento mas **custava 10 dias e 32 batidas** em outro.

Nenhum descarte por confiança — ver [Incerteza](#incerteza-o-caractere-).

---

## Estratégia dos parsers

Cada layout tem seu arquivo. Nenhuma regra é compartilhada "por semelhança".

**Detecção de coluna pelo cabeçalho, não por coordenada fixa.** As faixas saem
das posições reais das palavras do cabeçalho, medidas na própria página. É o
que impede, por exemplo, que as colunas `Jornada` e `Qtde` do `time-card-01` —
ambas no formato `HH:MM` — virem batidas. Um regex na linha produziria 153
falsas batidas nesse documento.

A comparação tolera erro de OCR: em `time-card-03` o Tesseract lê `Ent1` como
`Entl` e `Sai2` como `Sai?`, de forma idêntica nas 5 páginas. Exigir igualdade
tornaria o layout indetectável.

**Onde a faixa não serve, a leitura é estrutural.** Em `payroll-02` os títulos
são centralizados sobre colunas largas e a faixa cai no meio do nome da verba;
lá o parser lê por token. Em `payroll-01` os grupos são separados pela coluna
de código, cuja posição sai da mediana dos códigos do próprio documento.

### `kind` (IN/OUT) vem da coluna

Não da alternância por posição. Em `time-card-04` há linhas com células vazias
no meio: qualquer ausência deslocaria a paridade de todas as batidas seguintes.

### `date_raw` — dúvida levada à Quick Filler

Três dos quatro cartões imprimem só o dia na linha, com a competência no
cabeçalho. A dúvida foi enviada à equipe e respondida: **compor a data completa
quando a associação for segura; preservar o valor parcial quando houver
ambiguidade.**

`time-card-01` e `-02` compõem (`01/07/2012`). `time-card-03` já traz a data
completa. `time-card-04` **não compõe** — o mês é manuscrito ilegível.

---

## Incerteza: o caractere `?`

**Validação estrutural por posição.** Um campo com formato conhecido tem uma
classe de caractere esperada em cada posição; o que viola vira `?`, e **somente
aquela posição**.

**A confiança do Tesseract não é usada como filtro**, e isso foi medido. Em
`time-card-03`, sobre 822 horários lidos corretamente:

| | |
|---|---|
| confiança mínima | 0 |
| mediana | 91 |
| **lidos CERTO com confiança < 30** | **47** |

Os 4 tokens realmente errados têm confiança 25, 41, 44 e 53 — dentro da faixa
dos corretos. Um corte em 50 marcaria dezenas de valores corretos para pegar 4
errados. Há ainda o caso oposto: `Sai1` lido **errado** como `Sail` com
confiança **95**.

**Nada é descartado.** Um token com forma de valor nunca é jogado fora por estar
imperfeito. Antes dessa regra, `23:00c` lido como `23:00€` era descartado
silenciosamente e o documento perdia 4 batidas.

**Falso negativo conhecido:** dígito trocado por dígito (`07:00` → `01:00`)
passa pela validação. Não há como detectar sem uma segunda fonte de leitura.

---

## Avisos derivados

Calculados a partir do dado, **nunca armazenados** — funções puras em
`app/services/warnings_service.py`, consumidas por interface e planilha, para
que as duas nunca divirjam.

| Aviso | Cor |
|---|---|
| Batidas ímpares · página vazia · **qualquer `?` na linha** | amarelo `#FFF3CD` |
| Data ou mês não sequencial | vermelho `#F8D7DA` + borda `#DC3545` |

Vermelho ganha de amarelo. Dezembro → janeiro é sequência válida; competência
ilegível não quebra a cadeia.

**O destaque é derivado do dado estruturado, não do texto da célula.** Em
`time-card-03` a marcação vive só no `time_raw` (`23:00?`) enquanto a planilha
mostra `time_hhmm` (`23:00`). Procurar `?` na célula não encontraria nada.

---

## API

Contrato oficial, literal:

| | |
|---|---|
| `POST /api/transcricoes` | `multipart` com `arquivo` e `tipo` → **202** `{"id": "..."}` |
| `GET /api/transcricoes/{id}` | `{id, tipo, status, erro, value}` |
| `PUT /api/transcricoes/{id}` | `{"value": {...}}` substitui a transcrição |
| `GET /api/transcricoes/{id}/planilha?formato=xlsx\|csv\|json` | planilha com as correções |
| `GET /healthz` | 200 |

**Dois endpoints auxiliares**, que não substituem nenhum dos obrigatórios:

- `GET /api/transcricoes/{id}/revisao` — projeção em tabela com as colunas da
  planilha, severidade, motivos legíveis e o caminho de cada célula no `value`;
- `GET /api/transcricoes/{id}/arquivo` — o PDF original, `inline`.

Existem para a interface não reimplementar em JavaScript as colunas da planilha
e as quatro regras de aviso.

### Comportamentos não especificados pelo contrato

| Situação | Decisão |
|---|---|
| PUT enquanto `processando` | `409` — o pipeline sobrescreveria a correção |
| Planilha antes de `concluido` | `409` |
| `?formato` inválido / ausente | `400` / assume `xlsx` |
| CSV | separador `;`, `utf-8-sig` (padrão Excel pt-BR) |

---

## Processamento assíncrono

`BackgroundTasks` do FastAPI. O POST responde 202 imediatamente; o `status` no
banco é a fonte de verdade e o frontend faz polling com recuo progressivo.

Celery + Redis resolveriam o mesmo problema com dois serviços a mais. O
requisito é não processar dentro do request — não ter fila distribuída.

**Consequência assumida:** uvicorn com 1 worker.

---

## Persistência

SQLite, uma tabela, `value` como JSON serializado. Conexão por operação, com
WAL — uploads simultâneos e processamento em background exigem isso.

PostgreSQL seria a escolha certa com múltiplos workers ou volume real. Aqui
seria um serviço a mais no `docker compose up`, que é o requisito duro.

---

## Segurança

**Validação de upload, em três camadas:** tamanho cortado durante a leitura
(20 MB) → assinatura `%PDF-` nos bytes iniciais → abertura real com limite de
50 páginas. Extensão e `content-type` vêm do cliente e não valem como prova.

**PII em repouso:** PDFs `0600`, diretório `0700`, banco `0600`. O nome original
do upload **nunca** é gravado — costuma conter o nome da pessoa. O arquivo usa o
id opaco da transcrição.

**Logs sem PII:** só id, tipo, status, duração e nome do parser. O log de falha
usa `exc_info=False` de propósito: o traceback pode conter trechos do documento.

**Concorrência limitada.** Medido: 6 uploads simultâneos de um documento de 19 s
levaram 189 s — pior que em fila. Um semáforo limita o processamento; o
excedente espera com `status: processando`.

**Em produção:** a aplicação não é exposta diretamente. Bind em
`127.0.0.1:8002`, atrás do Nginx com HTTPS. Limite de memória no container
(`600m`) protege as aplicações vizinhas.

### Política de retenção

| | |
|---|---|
| **O que** | o PDF enviado e a transcrição (banco) |
| **Onde** | volume Docker: `/data/pdfs` e `/data/quickfiller.db` |
| **Por quanto tempo** | 24 h a partir do upload (`QF_RETENTION_HOURS`) |
| **Quando é removido** | na inicialização da aplicação e a cada novo upload |

Sem agendador: cron/Celery seriam três serviços para uma consulta de
milissegundos. **Limitação:** uma instância de pé por semanas sem nenhum upload
só limpa no próximo reinício.

---

## Testes

**194 testes.** O INSTRUCOES pede uma linha justificando cada caso; com esse
volume, a justificativa é por grupo — cada arquivo protege uma classe de erro
específica.

| Arquivo | Por que existe |
|---|---|
| `test_formato_oficial.py` | os exemplos **literais** do README validam contra os schemas — o teste mais barato contra o risco mais caro |
| `test_contrato_http.py` | 202, envelope com as 5 chaves, `erro` legível sem traceback |
| `test_upload_validacao.py` | o `.txt` renomeado que o INSTRUCOES cita nominalmente |
| `test_ciclo_completo.py` | "a correção chega na planilha?" — nos três formatos |
| `test_status_processando.py` | `value: null` enquanto processa |
| `test_extracted_page.py` / `test_columns.py` | agrupamento em linhas e faixas de coluna: se errarem, todo parser lê errado |
| `test_ocr.py` | **regressão**: palavra de confiança 10 precisa sobreviver |
| `test_uncertainty.py` | os dois lados da calibração — marcar o duvidoso E não marcar o que foi lido bem |
| `test_incerteza_documentos_reais.py` | **regressão**: as 4 batidas que eram perdidas em silêncio |
| `test_warnings_service.py` | dez→jan e competência ilegível: regras finas, fáceis de quebrar sem perceber |
| `test_destaques_xlsx.py` | cores inspecionadas célula a célula — o arquivo abrir não prova nada |
| `test_sipon.py` e demais parsers | armadilhas medidas em cada PDF real |
| `test_layouts_restantes.py` | **regressões** das três perdas silenciosas do bloco 2.5 |
| `test_seguranca.py` | concorrência limitada, permissões, retenção efetiva |
| `test_interface.py` | projeção de revisão coerente com a planilha |

Fixtures de OCR gravadas em `tests/fixtures/` — rodar Tesseract nas 5 páginas
leva ~26 s, e teste que não se roda não protege nada. O caminho de OCR real
continua coberto por um teste de integração.

---

## Deploy

```
Internet → HTTPS → Nginx (host) ─┬─ 127.0.0.1:8000 → outra aplicação
                                 └─ 127.0.0.1:8002 → Quick Filler
```

EC2 `t3.micro` (2 vCPU, ~912 MiB), Amazon Linux 2023, **compartilhada com outra
aplicação em produção**. TLS pelo Nginx + Certbot que já existiam na máquina —
introduzir um segundo proxy reverso exigiria as portas 80/443, já ocupadas.

Ajustes de capacidade: 2 GiB de swap, `vm.swappiness=10`, limite de 600 MiB no
container e concorrência 1.

**Medido em produção**, durante um OCR real: RAM disponível caiu de 313 para
~61–67 MiB, swap subiu a ~315–325 MiB, o container chegou a ~459–466 MiB de 600.
Sem OOM, sem reinício, aplicações vizinhas intactas. O swap voltou ao repouso
depois — funcionou como amortecedor de pico.

**A margem é estreita.** Adequada para demonstração e tráfego baixo; **não**
para concorrência real. Detalhes em [`deploy/README.md`](deploy/README.md).

---

## Assimetria entre os dois extratores — declarada

Os dois tipos pesam igual na nota, e **não estão no mesmo nível**.

**Holerite está mais completo:** 4 de 4 layouts, sendo 3 por texto nativo, onde
a fidelidade é alta.

**Cartão de ponto tem 3 de 4**, e o que falta é o mais difícil do conjunto.

Dentro de cada tipo há outra assimetria: texto nativo é fiel; OCR sobre PDF
vetorial é bom; scan real de papel é inviável com Tesseract.

---

## Limitações

**`time-card-04` não é transcrito.** Cartão de papel fotografado, com marcações
matriciais. **19 combinações** de DPI, modo de segmentação e pré-processamento
foram medidas: o melhor resultado recuperou **1 de ~48 horários**, e esse é
lixo (`42:62`).

As alternativas foram consideradas e rejeitadas: emitir os dias com
`punches: []` afirmaria que dias com 6 marcações não têm nenhuma — o "valor
errado com cara de certo" que o README chama de pior resultado. Marcar tudo com
`?` significa não ter transcrito nada. A resposta é dizer que não sabe ler.

**`payroll-04`: rótulos truncados no primeiro caractere** — `SR COMISSAO` (era
DSR), `ALE REFEICAO` (VALE). Como rótulo vira coluna de planilha, o cabeçalho
sai com essa grafia.

**`payroll-04`: ano lido errado** — `2016` no lugar de `2019` em três páginas.
Troca dígito-por-dígito: a validação estrutural não pega. **O aviso de mês não
sequencial sinaliza**, que é o comportamento projetado.

**`payroll-01`: rótulos com espaços colapsados** — `REMUNERAÇÃOMES`,
`BASEDECALCULODOINSS`. Não é OCR: vêm colados do próprio PDF nativo. Separar
exigiria um dicionário de termos, que quebraria no primeiro documento diferente.

**Outras:** CSV não carrega destaque visual (limitação do formato; o JSON
preserva tudo) · a interface não permite acrescentar uma batida faltante, só
corrigir as existentes · sem timeout de processamento · sem rate limiting ·
sem autenticação (o desafio dispensa login).

---

## O que foi cortado por tempo

- **CI** (lint + testes no GitHub Actions) — é diferencial, não requisito;
- **todos os bônus**: rastreabilidade visual, detecção automática de tipo,
  comportamento sofisticado para layout desconhecido;
- **calibração fina de OCR** por documento;
- **acabamento visual** da interface, deliberadamente: UI bonita não pode
  consumir tempo que deveria ir para extração.

## O que faria com mais tempo

1. **Atacar o `time-card-04`** com OCR especializado em dígitos matriciais ou
   serviço de nuvem — é a maior lacuna de precisão.
2. **Segunda fonte de leitura para os dígitos.** O falso negativo mais grave é
   dígito trocado por dígito. Ler a mesma região duas vezes com configurações
   diferentes e marcar divergências com `?` atacaria isso diretamente.
3. **Reconstruir rótulos colados** do `payroll-01` e os truncados do
   `payroll-04`, já que viram colunas de planilha.
4. **Rastreabilidade visual** — as coordenadas já atravessam o pipeline.
5. **Timeout de processamento** e rate limiting.

## O que mudaria no formato oficial

O cartão de ponto não tem campo normalizado para data — existe `time_raw` e
`time_hhmm`, mas só `date_raw`. Um `date_iso` resolveria a ambiguidade que
precisou ser levada à equipe, sem perder o valor impresso.
