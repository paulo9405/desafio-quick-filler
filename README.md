# Quick Filler — transcrição de documentos trabalhistas

Transcreve **cartões de ponto** e **holerites** em PDF para dados estruturados e
planilhas, com revisão humana antes do download.

**Aplicação publicada:** https://quickfiller.paulodev.net

Desafio técnico da [Quick Filler](https://github.com/quick-filler/desafio-programador).

---

## O problema

Documentos trabalhistas chegam em centenas de layouts, parte deles escaneados,
e a leitura automática erra. A exigência do domínio é que **um número errado
nunca passe despercebido** — pior que um campo vazio é um campo errado com
aparência de certo.

Daí as três características centrais da solução:

- o par `_raw` / normalizado, para auditar o que foi lido contra o que foi
  interpretado;
- o marcador `?`, por caractere, onde a leitura não foi confiável;
- avisos derivados que destacam o que precisa de olho humano.

---

## Como executar

```bash
docker compose up
```

Aplicação em **http://localhost:8000**. A imagem já traz Tesseract e o idioma
português — nada a instalar no host.

Testes:

```bash
docker run --rm -v "$PWD":/srv -w /srv quick-filler-app python -m pytest
```

**194 testes.**

---

## Fluxo

```
enviar PDF → processar → revisar e corrigir → baixar planilha
```

Na interface: escolher o PDF e o tipo, acompanhar o processamento, revisar a
tabela **ao lado do PDF original**, corrigir células e baixar em XLSX, CSV ou
JSON já com as correções.

Documentos escaneados passam por OCR e levam dezenas de segundos — o
processamento roda em segundo plano e a tela acompanha o estado.

---

## Arquitetura

```
PDF
 ↓  validação (tamanho · assinatura · abertura real)
 ↓  extração — a página tem camada de texto útil?
     ├── sim → pdfplumber
     └── não → pypdfium2 (300dpi) → Tesseract
 ↓  ExtractedPage[]   ← palavras + coordenadas + confiança
 ↓  registry → parser do layout
 ↓  SQLite
 ↓
 ├── interface de revisão (edição → PUT)
 └── avisos derivados → xlsx · csv · json
```

**Um pipeline, dois extratores.** O que muda entre os tipos é o parser e o
formato da planilha; o resto é compartilhado.

**Stack:** Python · FastAPI · pdfplumber · pypdfium2 · Tesseract · openpyxl ·
SQLite · HTML + Bootstrap + JavaScript puro · Docker.

Detalhes de engenharia e justificativas em **[`SOLUCAO.md`](SOLUCAO.md)**.

---

## API

| Endpoint | |
|---|---|
| `POST /api/transcricoes` | `multipart` com `arquivo` e `tipo` → **202** `{"id"}` |
| `GET /api/transcricoes/{id}` | `{id, tipo, status, erro, value}` |
| `PUT /api/transcricoes/{id}` | `{"value": {...}}` substitui a transcrição |
| `GET /api/transcricoes/{id}/planilha?formato=xlsx\|csv\|json` | planilha com as correções |
| `GET /healthz` | 200 |

`status` ∈ `processando` · `concluido` · `erro`. Enquanto `processando`,
`value` é `null`.

Dois endpoints auxiliares servem a interface e não substituem nenhum dos
acima: `/revisao` (tabela + avisos) e `/arquivo` (PDF original).

Documentação interativa em `/docs`.

---

## Cobertura dos documentos oficiais

| Documento | Extração | Resultado |
|---|---|---|
| `time-card-01` | texto nativo | 153 dias · 369 batidas |
| `time-card-02` | OCR | 153 dias · 372 batidas |
| `time-card-03` | OCR | 280 dias · 826 batidas · 4 com `?` |
| `time-card-04` | OCR | **não suportado** |
| `payroll-01` | texto nativo | 30 entradas · 455 verbas |
| `payroll-02` | texto nativo | 10 entradas · 92 verbas |
| `payroll-03` | texto nativo | 5 entradas · 44 verbas |
| `payroll-04` | OCR | 5 entradas · 42 verbas |

**7 de 8.** O oitavo é um cartão de papel fotografado que o Tesseract não lê —
a aplicação responde que não sabe ler, em vez de inventar dados. Justificativa
com as medições em [`SOLUCAO.md`](SOLUCAO.md#limitações).

---

## Validações e limites

| | |
|---|---|
| Tamanho do upload | 20 MB, cortado durante a leitura |
| Páginas por PDF | 50 |
| Tipo de arquivo | assinatura `%PDF-`, não a extensão |
| Processamento simultâneo | 1 em produção, 2 local |
| Retenção | 24 h, aplicada na subida e a cada upload |

Um `.txt` renomeado para `.pdf` é recusado com `400`. PDF corrompido também.

Configuração por variáveis de ambiente (`QF_*`), todas com padrão — ver
`docker-compose.yml`. Nenhum segredo no repositório.

---

## Persistência

SQLite e os PDFs enviados vivem num volume Docker (`/data`). Os arquivos
guardam PII, então são gravados com permissão restrita e o nome original do
upload nunca é preservado.

---

## Limitações conhecidas

- **`time-card-04` não é transcrito** — 19 configurações de OCR medidas, melhor
  resultado 1 de ~48 horários;
- `payroll-04`: rótulos truncados no primeiro caractere e ano lido errado em
  três páginas (o aviso de mês não sequencial sinaliza);
- `payroll-01`: rótulos com espaços colapsados vindos do próprio PDF;
- CSV não carrega destaque visual — o JSON preserva tudo;
- sem timeout de processamento, rate limiting ou autenticação.

Lista completa em [`SOLUCAO.md`](SOLUCAO.md#limitações).

---

## Estrutura

```
app/
├── api/            rotas e injeção de dependências
├── core/           configuração e logging
├── extraction/     ExtractedPage, texto nativo, OCR, detecção de coluna
├── parsers/        um arquivo por layout + registry
│   ├── timesheet/  sipon · cartao_ponto_tabular · ponto_eletronico
│   └── payslip/    demonstrativo_mensal · recibo_pagamento
│                   declaracao_remuneracao · ficha_financeira
├── repositories/   SQLite
├── schemas/        formato oficial de saída
├── services/       documento, transcrição, avisos, exportação, revisão
└── static/         interface

deploy/             Nginx e guia de publicação
docs/               PROCESSO.md e roadmap
tests/              194 testes + fixtures de OCR
```

**Adicionar um layout novo:** criar um arquivo em `app/parsers/<tipo>/` e
registrá-lo em `app/parsers/registry.py`. Nada mais muda.

---

## Documentação

| | |
|---|---|
| [`SOLUCAO.md`](SOLUCAO.md) | como o sistema funciona, decisões e trade-offs |
| [`docs/PROCESSO.md`](docs/PROCESSO.md) | como foi desenvolvido, uso de IA, erros e medições |
| [`deploy/README.md`](deploy/README.md) | publicação em EC2 com Nginx |
