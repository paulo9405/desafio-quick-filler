# PROCESSO.md

Documentação do processo de desenvolvimento assistido por IA, conforme exigido
pelo README oficial da Quick Filler.

> **Status:** em construção. Escrito ao longo da implementação, não no final.
> Os registros abaixo são reais e datados; nada aqui foi reconstruído de
> memória depois do fato.

> **Nota de entrega:** este arquivo está em `docs/PROCESSO.md`. A lista oficial
> de entregáveis nomeia `PROCESSO.md` sem caminho, e o avaliador pode procurá-lo
> na raiz do repositório. Antes da entrega, decidir entre mover para a raiz ou
> deixar um ponteiro na raiz apontando para cá.

---

## 1. Ferramentas utilizadas

| Ferramenta | Para quê |
|---|---|
| **Claude Code (Opus)** | Agente principal de desenvolvimento: análise dos documentos oficiais e dos PDFs, revisão do roadmap, implementação, testes e validação em container. |
| **Docker / Docker Compose** | Ambiente de execução e de teste. O ambiente local tem Python 3.9 e não tem Tesseract; tudo roda no container para ter paridade com o `docker compose up` que a Quick Filler vai executar. |
| **poppler-utils** (`pdftotext`, `pdfinfo`, `pdffonts`, `pdfimages`, `pdftoppm`) | Só na fase de **análise** dos 8 PDFs: verificar camada de texto, fontes embutidas, imagens e renderizar páginas para inspeção visual. Não é dependência da aplicação. |

Ferramentas de linha de comando de análise foram usadas para **entender** os
documentos, não para processá-los na aplicação. A aplicação usa `pdfplumber` e
`pypdfium2`.

---

## 2. Linha do tempo do trabalho

Tempo real controlado pelo candidato — os campos de duração são preenchidos por
ele, não pelo agente.

### Sessão 1 — 12/08/2026

**Objetivo:** análise inicial, correção do roadmap e início da Fase 1.

| Bloco | Descrição | Tempo |
|---|---|---|
| 1.0 | Análise dos documentos oficiais (README, INSTRUCOES, repositório) e dos 8 PDFs | _(a preencher)_ |
| 1.1 | Revisão do `docs/roadmap.md` com as correções D1–D12 | _(a preencher)_ |
| 1.2 | Fase 1, bloco 1: fundação FastAPI + Docker + Tesseract + `/healthz` | _(a preencher)_ |
| 1.3 | Fase 1, bloco 2: contrato HTTP + persistência + processamento assíncrono | _(a preencher)_ |

**Tempo acumulado:** _(a preencher)_

---

## 3. Decisões técnicas registradas

Cada uma tinha mais de uma resposta razoável. A alternativa descartada está
registrada junto, porque é ela que torna a decisão discutível.

### 3.1 SQLite em vez de PostgreSQL

**Escolha:** SQLite, uma tabela, `value` guardado como JSON serializado.

**Alternativa:** PostgreSQL com JSONB.

**Por quê:** o INSTRUCOES afirma que banco é opcional — precisa funcionar entre
o envio e o download, com política de retenção escrita. A persistência
necessária é um documento JSON por transcrição. Um serviço a menos deixa o
`docker compose up` mais rápido e mais confiável, e esse é o requisito duro do
desafio. PostgreSQL seria a escolha certa com múltiplos workers ou volume real.

**Limitação assumida:** um único processo escrevendo. Escalar horizontalmente
exigiria trocar o repositório — que é o único ponto que conhece SQL.

### 3.2 `pdfplumber` + `pypdfium2` em vez de PyMuPDF

**Escolha:** duas bibliotecas, uma para extrair palavras com coordenadas e
outra para renderizar páginas.

**Alternativa:** PyMuPDF, que faria as duas coisas com uma API mais confortável.

**Por quê:** foi dada preferência a bibliotecas com licenças permissivas e
adequadas ao contexto de distribuição do desafio, além dos requisitos técnicos
de extração e renderização. A API de palavras do `pdfplumber` também é mais
direta para estender um layout novo durante a sessão técnica ao vivo.

### 3.3 `BackgroundTasks` em vez de fila externa

**Escolha:** `BackgroundTasks` do FastAPI, com o `status` no banco como fonte
de verdade e polling do frontend.

**Alternativa:** Celery + Redis.

**Por quê:** atende ao requisito real (não processar dentro do request, porque
o proxy da plataforma corta a conexão) sem adicionar dois serviços. O
INSTRUCOES pede que a aplicação sobreviva a um documento demorado, não que ela
tenha fila distribuída.

**Consequência assumida:** uvicorn roda com **1 worker**. Mais workers com
`BackgroundTasks` + SQLite exigiriam coordenação que não existe aqui. Está
explícito no `Dockerfile`.

### 3.4 Tesseract instalado já na Fase 1

**Por quê:** é a dependência de sistema com maior chance de quebrar build e
deploy. Descobrir isso no início custa minutos; descobrir na Fase 3, junto com
o deploy, custa a entrega. Validado no container: Tesseract 5.5.0 com o idioma
`por` disponível.

### 3.5 `value` do PUT aceito como objeto livre

**Escolha:** o PUT valida que `value` é um objeto, mas não impõe o schema do
parser.

**Por quê:** `value` carrega correções feitas por uma pessoa. Validar
rigidamente arriscaria rejeitar uma correção legítima — inclusive a correção de
um campo que a máquina leu com formato inesperado. A honestidade dos dados vale
mais que a rigidez do schema neste ponto.

### 3.6 Comportamentos não especificados pelo contrato

O contrato oficial não define estes casos. Foram decididos e registrados:

| Situação | Decisão | Motivo |
|---|---|---|
| PUT enquanto `status = processando` | `409` | O pipeline sobrescreveria o que a pessoa digitou. |
| Planilha antes de `concluido` | `409` com o status atual na mensagem | Não existe transcrição para exportar. |
| `?formato` inválido | `400` | Erro do cliente, não do servidor. |
| `?formato` ausente | assume `xlsx` | O README chama `xlsx` de formato preferido. |
| CSV: separador e encoding | `;` e `utf-8-sig` | Padrão do Excel pt-BR; os valores monetários já usam vírgula decimal. |

### 3.7 Retenção aplicada de forma oportunista

**Escolha:** a limpeza de transcrições expiradas roda em background a cada
upload.

**Alternativa:** um agendador (cron, APScheduler).

**Por quê:** o desafio pede política de retenção definida e aplicada, não
infraestrutura de agendamento.

**Limitação conhecida e assumida:** uma instância que nunca recebe upload nunca
limpa. Para o volume deste projeto é aceitável.

---

### 3.8 Ambiguidade de `date_raw` levada ao responsável pelo requisito (P1)

Este item não registra um erro, e sim o tratamento de uma ambiguidade real da
especificação.

**A ambiguidade.** Durante a análise dos 8 documentos, três dos quatro cartões
de ponto mostraram que a linha traz apenas o dia (`01`), enquanto mês e ano
aparecem separadamente no cabeçalho da página. O README define `date_raw` como
"a data exatamente como está impressa, sem normalizar", e o formato de cartão de
ponto não possui campo normalizado equivalente ao `time_hhmm` — não há onde
colocar uma data composta.

**As duas interpretações razoáveis.**

1. preservar exatamente o valor da linha, `"01"`;
2. compor a data com a competência do cabeçalho, `"01/07/2012"`.

Ambas são defensáveis: a primeira é a leitura literal de "exatamente como está
impressa"; a segunda produz o dado que a planilha e a verificação de data
sequencial realmente precisam.

**A decisão foi deixada deliberadamente em aberto.** A pendência foi registrada
como P1 em `docs/roadmap.md` seção 2.2, com instrução explícita de não
implementar nenhuma das alternativas até haver definição. As Fases seguintes do
bloco de implementação foram conduzidas normalmente, porque nenhuma delas
dependia dessa resposta — só o parser de cartão de ponto dependia.

**Consulta ao responsável pelo requisito.** A dúvida foi enviada diretamente à
equipe da Quick Filler antes de consolidar qualquer comportamento. O próprio
README incentiva isso: "perguntar quando o enunciado está ambíguo é
comportamento desejável, não sinal de fraqueza".

**Resposta oficial.** A Quick Filler confirmou que **as duas abordagens seriam
aceitas**, e indicou que a data completa é o melhor resultado quando dia, mês e
ano puderem ser associados à linha com segurança, com a ressalva de evitar
completar informação quando houver ambiguidade ou incerteza.

**Implementação.** A preferência indicada foi adotada, mantendo o valor parcial
quando a associação não for segura:

| Documento | Competência no cabeçalho | `date_raw` |
|---|---|---|
| `time-card-01` | `Mes/Ano : 7 / 2012`, legível | `"01/07/2012"` — composta |
| `time-card-02` | `Mês/Ano: 05/2010`, legível | composta (Fase 2) |
| `time-card-03` | data completa já na linha | não se aplica |
| `time-card-04` | manuscrita ilegível / em branco | só o dia — **não compõe** |

No parser SIPON isso vive numa única função, `_montar_date_raw`, que devolve o
dia impresso quando a competência não pôde ser lida. Não existe caminho em que
o parser "chute" mês ou ano. Coberto por dois testes, um para cada ramo.

**O que este item registra como processo:** identificação de ambiguidade →
avaliação das alternativas → validação com o responsável pelo requisito →
decisão documentada → implementação.

---

## 4. Erros e caminhos errados do agente

Registro honesto, feito no momento em que cada um aconteceu.

### 4.1 Trabalhar a partir de uma versão traduzida e resumida da especificação

**O que aconteceu:** na primeira leitura da documentação oficial, o agente
buscou o `README.md` e o `INSTRUCOES.md` por uma ferramenta que converte a
página e a resume com um modelo auxiliar. O resultado voltou **traduzido para
inglês e resumido**: `"Salário Base"` virou `"Base Salary"`, `"Base INSS"`
virou `"INSS Base"`, e o `INSTRUCOES.md` voltou como um resumo em prosa em vez
do texto literal.

**Por que era grave:** os labels do holerite viram **nomes de coluna da
planilha**, e a lista de erros comuns do INSTRUCOES é praticamente uma
checklist de avaliação. Implementar a partir dessa versão significaria produzir
labels errados e perder regras específicas.

**Como foi percebido:** o texto voltou limpo demais e em inglês, sendo que o
desafio é escrito em português. A tabela de pesos aparecia parafraseada, não
como tabela.

**Correção:** baixar os arquivos crus com `curl` a partir de
`raw.githubusercontent.com` e lê-los diretamente. Só então apareceram detalhes
que o resumo tinha perdido — entre eles o fundo `#173772` do cabeçalho, a regra
de dezembro→janeiro e a regra de que competência ilegível não quebra a cadeia.

**Aprendizado:** para especificação normativa, ler a fonte crua. Resumo de
especificação é perda de requisito.

### 4.2 Alias de tipo que não era um tipo

**O que aconteceu:** ao escrever `document_service.py`, o agente produziu:

```python
def remove(self, caminho: Optional_str) -> None: ...

# no fim do arquivo
Optional_str = "str | None"
```

Isso é uma string solta fingindo ser uma anotação de tipo, definida **depois**
do uso, com o comentário de que serviria "para não importar typing no topo" —
sendo que `typing` já estava importado no arquivo.

**Como foi percebido:** relendo o arquivo antes de rodar qualquer coisa.

**Correção:** `Optional[str]` com o import correto, e o método virou
`@staticmethod`, que era o que ele já deveria ser.

**Aprendizado:** o agente às vezes inventa uma justificativa plausível para uma
construção que não faz sentido. A justificativa soar razoável não é evidência
de que o código está certo.

### 4.3 Teste que teria passado pelo motivo errado

**O que aconteceu:** o plano era testar por HTTP a regra
`status = processando → value = null`, enviando um PDF e consultando o GET
logo em seguida.

**Por que estava errado:** o `TestClient` do FastAPI executa as background
tasks **antes** de devolver a resposta do POST. Quando o GET acontece, o
processamento já terminou, e o status nunca é `processando`. O teste passaria —
mas sem nunca ter exercitado a regra que dizia proteger.

**Como foi percebido:** ao rodar a suíte, o teste de erro de layout passou
imediatamente, o que só é possível se o processamento já tiver ocorrido dentro
do POST.

**Correção:** a garantia passou a ser testada diretamente, em
`tests/api/test_status_processando.py`: um registro recém-criado fica
`processando` com `value` nulo, e o serializador força `value = None` mesmo que
houvesse valor gravado. O motivo de não testar por HTTP está escrito no próprio
arquivo de teste.

**Aprendizado:** teste verde não é evidência de cobertura. Vale perguntar por
que ele passou.

### 4.4 Limiar de confiança que apagava dados corretos — o pior erro até agora

**O que aconteceu:** ao escrever o caminho de OCR, o agente adicionou um filtro
descartando toda palavra com confiança do Tesseract abaixo de 30, com um
comentário justificando que seriam "ruído de borda, carimbo ou artefato de
digitalização". O número não veio de medição nenhuma — foi inventado, e a
justificativa foi escrita depois, para acompanhá-lo.

**Por que era grave:** medindo a saída real do Tesseract em `time-card-03`, o
filtro apagava **batidas corretas**:

```
' 07:00d'  conf=10   leitura correta, descartada
' 15:00d'  conf=16   leitura correta, descartada
' 06:59d'  conf=9    leitura correta, descartada
' 06:59d'  conf=13   leitura correta, descartada
'23:00€'   conf=25   leitura errada — caso de `?`, não de descarte
```

Uma página perdia batidas sem nenhum sinal. É literalmente o erro que o
INSTRUCOES nomeia — "perder linhas em silêncio" — e o oposto da regra central
do desafio, que é nunca descartar em vez de marcar incerteza.

**Como foi percebido:** comparando a saída do OCR com a renderização da página.
A linha `19/12/2019` do `time-card-03` devolveu 3 batidas, e o documento mostra
4. A diferença foi notada porque as linhas vizinhas (`18/12` e `20/12`) tinham
4, o que tornava a lacuna visível.

**Investigação:** um script imprimiu todas as palavras daquela linha com suas
confianças, sem filtro. O `07:00d` estava lá, correto, com confiança 10.

**Correção:** o limiar foi removido por completo. O único descarte que
permanece é `conf = -1`, que o Tesseract usa para marcar bloco e parágrafo — não
são palavras. Toda palavra lida é preservada com sua confiança, e a decisão de
marcar `?` fica para a Fase 2, que é onde ela pertence. Glifos de borda de
tabela (`|`, `—`) também ficam: o parser os ignora por posição de coluna, e
mantê-los é mais seguro do que arriscar apagar dado.

**Teste de regressão:** `tests/extraction/test_ocr.py::test_palavra_de_baixa_confianca_e_preservada`,
com os valores reais do caso.

**Aprendizado:** o agente produz constantes com aparência de decisão técnica e
escreve uma justificativa convincente para elas. Toda constante que descarta
dado precisa de medição, não de comentário. E vale repetir o padrão do erro
4.2: a justificativa soar razoável não é evidência de que está certa.

### 4.5 `--psm 3` vs `--psm 6`: decisão tomada por medição

Não foi um erro, mas registra o método oposto ao do item anterior.

O modo de segmentação de página do Tesseract foi escolhido comparando os dois
candidatos na mesma página real (`time-card-03`, página 1):

| | palavras | confiança média | tempo | datas |
|---|---|---|---|---|
| `--psm 3` (padrão) | 431 | 89.5 | 48.3s | `16/ 2/20 dO` — quebradas |
| `--psm 6` | 643 | 87.2 | 25.9s | `16/12/2019` — corretas |

A conclusão registrada é restrita ao que foi medido: **para os documentos
testados neste desafio**, `--psm 6` apresentou melhor resultado prático e menor
tempo. Não se conclui daqui que `psm 6` seja universalmente melhor — o modo
adequado depende da estrutura da página, e estes documentos são tabulares.

Ficou como padrão, configurável por `QF_OCR_PSM` justamente para poder ser
revisto quando aparecer um documento de estrutura diferente.

Aprendizado registrado: a confiança média de `psm 3` foi **maior** (89,5 contra
87,2) e ainda assim o resultado foi pior — as datas saíram quebradas. Confiança
média não é medida de qualidade de transcrição, e usá-la como critério de
escolha teria levado à decisão errada.

### 4.6 `@app.on_event("startup")` deprecado

**O que aconteceu:** a inicialização foi escrita com `@app.on_event`, que está
deprecado no FastAPI.

**Como foi percebido:** revisão do bloco antes de fechá-lo.

**Correção:** trocado por `lifespan`, o idioma atual. Sem impacto funcional.

**Registro:** erro menor, anotado para não inflar a lista com algo que foi
apenas desatualização de API.

---

## 5. Código escrito ou reescrito à mão pelo candidato

_(a preencher pelo candidato ao longo da implementação)_

---

## 6. Respostas às perguntas do desafio

### 6.1 Três decisões em que havia mais de uma resposta razoável

_(a consolidar no fim do projeto, a partir da seção 3 — as candidatas mais
fortes hoje são 3.1 SQLite, 3.2 bibliotecas de PDF e 3.3 processamento
assíncrono, mas decisões de interpretação da especificação podem se mostrar
mais interessantes que as de infraestrutura.)_

### 6.2 O que quebra primeiro em produção?

_(resposta final no fim do projeto. Hipóteses atuais, a confirmar:_

- _a precisão do OCR em `time-card-04`, único scan real do conjunto;_
- _um layout desconhecido chegando em produção — hoje isso termina em `erro`
  explicado, que é o comportamento correto, mas significa documento não
  transcrito;_
- _a limpeza de retenção, que só roda quando há upload.)_

### 6.3 Onde você não confia no que entregou?

_(resposta final no fim do projeto.)_

---

## 7. Estado atual da implementação

**Fase 1 — em andamento.**

| Bloco | Estado |
|---|---|
| 1/4 — Fundação, Docker, Tesseract, `/healthz` | concluído e validado |
| 2/4 — Contrato HTTP, persistência, processamento assíncrono | concluído e validado |
| 3/4 — Extração (`ExtractedPage`: texto nativo + OCR) | concluído e validado |
| 4/4 — Registry + primeiro parser real (SIPON) | concluído e validado |

**Fase 1 concluída**, aguardando revisão e autorização para a Fase 2.

Resultado do bloco 4/4, medido contra `time-card-01.pdf`:

- 5 páginas, 153 dias, 369 batidas;
- dias por página (31, 31, 30, 31, 30) conferem com o calendário de julho a
  novembro de 2012;
- nenhuma data duplicada, nenhuma linha perdida;
- zero falsas batidas vindas das colunas `Jornada` e `Qtde`;
- `date_raw` composto como `01/07/2012`, conforme a regra da P1.

**Pendência P1 (`date_raw`) — RESOLVIDA em 12/08/2026.**

A dúvida sobre o que colocar em `date_raw` nos documentos que imprimem apenas o
dia na linha, com mês e ano no cabeçalho da página, foi levantada durante a
análise inicial, enviada à Quick Filler e respondida oficialmente.

A resposta aceitou as duas abordagens e indicou que compor a data completa é o
melhor resultado **quando dia, mês e ano puderem ser associados com segurança**,
com a ressalva explícita de não completar informação quando houver ambiguidade
ou incerteza.

Regra adotada, registrada em `docs/roadmap.md` seção 2.2:

1. associação segura → `date_raw` recebe a data completa;
2. associação insegura → preservar só o valor disponível na linha;
3. nunca inferir mês/ano sob ambiguidade — esta regra tem precedência.

Consequência prática: `time-card-01` e `time-card-02` compõem a data;
`time-card-04` não compõe, porque o mês é manuscrito ilegível numa página e
está em branco na outra.

Vale registrar o processo em si: perguntar em vez de assumir custou uma
mensagem e eliminou o risco de implementar uma interpretação errada de um campo
que aparece em toda linha de todo cartão de ponto.
