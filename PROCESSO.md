# PROCESSO.md

Documentação do processo de desenvolvimento assistido por IA, conforme exigido
pelo README oficial da Quick Filler.

> **Como ler este arquivo.** Ele foi escrito ao longo da implementação, não no
> final. As seções 3 e 4 são o registro corrido do trabalho — decisões e erros
> anotados quando aconteceram, com as medições que os sustentam. As seções 5 e 6
> são o fechamento, consolidado no fim a partir desse registro.
> Nada aqui foi reconstruído de memória depois do fato.

---

## 1. Ferramentas utilizadas

| Ferramenta | Para quê |
|---|---|
| **Claude Code (Opus)** | Agente principal de desenvolvimento: análise dos documentos oficiais e dos PDFs, revisão do planejamento interno, implementação, testes e validação em container. |
| **Docker / Docker Compose** | Ambiente de execução e de teste. O ambiente local tem Python 3.9 e não tem Tesseract; tudo roda no container para ter paridade com o `docker compose up` que a Quick Filler vai executar. |
| **poppler-utils** (`pdftotext`, `pdfinfo`, `pdffonts`, `pdfimages`, `pdftoppm`) | Só na fase de **análise** dos 8 PDFs: verificar camada de texto, fontes embutidas, imagens e renderizar páginas para inspeção visual. Não é dependência da aplicação. |

Ferramentas de linha de comando de análise foram usadas para **entender** os
documentos, não para processá-los na aplicação. A aplicação usa `pdfplumber` e
`pypdfium2`.

O uso de IA aqui foi intensivo, não acessório: **todo o código foi produzido
com o agente.** A divisão exata do trabalho — o que coube a mim e o que coube a
ele — está na [seção 5](#5-o-que-foi-reescrito-à-mão-e-por-quê), e os pontos em
que ele errou estão na seção 4.

---

## 2. Linha do tempo do trabalho

**Nota de método.** O tempo por bloco não foi cronometrado durante o trabalho.
Em vez de reconstruir durações de memória no fim — que seria inventar precisão
que nunca existiu — esta seção registra duas coisas que são verificáveis: o
horário real dos commits, e a estimativa de tempo efetivo informada pelo
candidato.

### Duas sessões, pelos commits

O histórico do Git é o registro objetivo. Cada linha marca o commit que fechou a
etapa.

| | 12/08/2026 — sessão 1 | 13/08/2026 — sessão 2 |
|---|---|---|
| Início | 08:38 workspace inicial | 09:05 stack de deploy |
| | 09:49 fundação + Docker + Tesseract | 10:23 adaptação ao Nginx da EC2 |
| | 10:14 contrato HTTP + persistência | 11:01 medições reais da EC2 |
| | 10:46 extração (nativo + OCR) | 11:15 README + SOLUCAO |
| | 11:13 registry + primeiro parser | 11:48 planilhas dos exemplos |
| | 11:51 cobertura dos dois tipos | |
| | 12:55 incerteza `?` | |
| | 13:07 avisos + destaques | |
| | 14:28 interface de revisão | |
| | 16:08 layouts restantes | |
| | 17:11 configurações no compose | |
| Fim | 18:18 concorrência + permissões | |
| **Decorrido** | **~9h40** | **~2h45** |

**Decorrido não é tempo efetivo.** Esses intervalos incluem pausas, refeições e
o tempo em que a máquina rodava OCR sozinha.

### Tempo efetivo

**Até o bloco 27.3 (deploy): ~8 horas efetivas.** Estimativa do candidato,
descontando as pausas. Não há precisão maior que essa, e fabricá-la seria pior
que a estimativa.

Contra o orçamento de ~14 h sugerido pela Quick Filler, isso deixou a margem que
cobriu deploy, documentação, planilhas dos exemplos e revisão final.

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
como P1 no planejamento interno, com instrução explícita de não implementar
nenhuma das alternativas até haver definição. As Fases seguintes do
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

### 3.9 Tolerância a erro de OCR no cabeçalho da tabela (bloco 2.1)

**O problema, medido.** A detecção de coluna do bloco 4/4 exigia que os títulos
do cabeçalho casassem exatamente. Ao aplicar isso em `time-card-03`, que é lido
por OCR, o cabeçalho não foi encontrado — porque **o Tesseract erra o próprio
cabeçalho**, de forma idêntica nas 5 páginas:

| Impresso | Lido | Confiança |
|---|---|---|
| `Ent1` | `Entl` | 66 |
| `Sai1` | `Sail` | **95** |
| `Sai2` | `Sai?` | 72 |

**Decisão.** Passar a casar por similaridade, com limiar 0.7. Cada um desses
casos tem similaridade 0.75 com o título correto.

**Alternativa descartada:** declarar no parser uma lista de apelidos
(`Ent1` também aceita `Entl`). Seria gravar no código os erros de OCR
observados num documento específico — exatamente o "ajustar o código ao PDF de
exemplo" que o INSTRUCOES lista entre os erros que derrubam entregas. Um
documento novo com outro erro de OCR voltaria a quebrar.

**Salvaguarda contra o risco introduzido.** Tolerância aumenta a chance de uma
linha qualquer casar por acaso. Para reduzir isso, `detect_columns` passou a
escolher a linha de **maior similaridade média**, e não a primeira que casa —
assim o cabeçalho de verdade ganha de um casamento marginal. Coberto por teste.

**Observação que reforça o item 4.4:** `Sail` foi lido **errado com confiança
95**. É a segunda evidência independente, no mesmo projeto, de que a confiança
do Tesseract não mede correção.

### 3.10 Decisões P2 resolvidas com evidência do `payroll-03`

**Linha `Total` com dois valores.** O documento imprime o rótulo `Total` uma
vez só, sob as colunas `Proventos` e `Descontos`, com um valor em cada.

- Alternativa A: emitir duas bases chamadas apenas `"Total"` — ambíguo, o
  consumidor não distingue qual é qual.
- Alternativa B (adotada): compor o label com o título da coluna, resultando em
  `"Total Proventos"` e `"Total Descontos"`.

Nada é inventado: os dois termos estão impressos no documento. O vocabulário
resultante coincide com o do exemplo oficial do README, que usa
`"Total Vencimentos"` e `"Total Descontos"` como bases.

**Base sem valor.** `Base I.R.R.F. 13o.:` aparece com rótulo e sem valor, em
todas as páginas. Adotado: preservar como base com `value` vazio. Omitir
esconderia que o documento traz o rótulo, e incluir não afeta a planilha,
porque bases não viram colunas.

### 3.11 Colunas finais declaradas só para limitar a faixa da última

Em `time-card-03`, as colunas `H.Ext`, `Atraso`, `Falta`, `Ad.Not` e `Abono`
contêm valores no formato `HH:MM` que **não são batidas**.

Como a faixa da última coluna declarada se estende até a borda da página, parar
a declaração em `Sai4` faria a faixa dela engolir a hora extra — e `07:00` da
coluna `H.Ext` viraria batida.

Decisão: declarar as cinco colunas finais no cabeçalho mesmo sem lê-las. Elas
existem apenas para delimitar `Sai4`. Está escrito no próprio parser, e há teste
usando `01/01/2020`, que tem `07:00` em `H.Ext` e apenas duas batidas reais.

### 3.12 Fixture de extração para os testes de parser sobre OCR

Rodar OCR nas 5 páginas de `time-card-03` leva ~26 s. Repetir isso a cada
execução tornaria a suíte cara demais — e teste que não se roda não protege.

Decisão: gravar a extração real do Tesseract como fixture
(`tests/fixtures/time-card-03.json.gz`, 29 KB) e testar o **parser** contra ela.
O caminho de OCR de verdade continua coberto por um teste de integração que
processa uma página real.

É o mesmo movimento previsto para receber um layout novo na sessão ao vivo:
analisar o documento, criar a fixture, criar o teste, implementar o parser. `tests/fixtures/gerar.py` regera quando necessário.

### 3.13 Estratégia de incerteza: validação estrutural, não confiança (bloco 2.2)

**A decisão.** A marcação `?` é feita por **validação estrutural por posição**:
um campo com formato conhecido (horário, valor monetário) tem uma classe de
caractere esperada em cada posição, e o que viola essa classe — e só isso —
vira `?`.

**A alternativa óbvia, e por que foi rejeitada com dado.** O caminho natural
seria `confiança < X → marcar ?`. Medição em `time-card-03`, sobre 822
horários lidos corretamente numa coluna de batida:

| | |
|---|---|
| confiança mínima | 0 |
| percentil 10 | 55 |
| mediana | 91 |
| **lidos CERTO com confiança < 30** | **47** |

E os 4 tokens realmente errados do mesmo documento têm confiança 25, 41, 44 e
53 — dentro da faixa dos corretos. Um corte em 50 marcaria dezenas de valores
corretos para pegar 4 errados. As distribuições se sobrepõem; a confiança não
separa certo de errado nestes documentos.

Somam-se os dois contraexemplos já registrados: valores corretos com confiança
9, 10 e 16 (item 4.4) e `Sai1` lido errado como `Sail` com confiança 95
(item 3.9).

**O que a regra encontrou nos documentos reais.** Exatamente 4 casos, todos em
`time-card-03`: `23:00c` e `15:12c` com o marcador lido como `€`.

**Efeito colateral que era um bug sério.** Esses 4 tokens não eram só
"não marcados" — eram **descartados**. O parser exigia casamento estrito com o
padrão de horário e jogava fora o que não casasse. O documento perdia 4 batidas
sem qualquer sinal, que é o erro que o INSTRUCOES chama de "perder linhas em
silêncio".

Depois da mudança: `time-card-03` passou de 822 para **826 batidas**.

**Impacto medido nos outros documentos** — a mudança tinha que afetar só os 4
casos conhecidos:

| Documento | Antes | Depois |
|---|---|---|
| `time-card-03` (OCR) | 822 batidas | 826, sendo 4 marcadas |
| `time-card-01` (nativo) | 153 dias / 369 batidas | idêntico, 0 marcações |
| `payroll-03` (nativo) | 44 verbas | idêntico, 0 marcações |

**Horário impossível.** `25:00` é erro de leitura, não horário — o README é
explícito quanto a datas, e o mesmo raciocínio vale aqui. O componente
impossível vira `??` no normalizado, porque sabemos que está errado mas não
qual dígito é o certo. O valor lido continua íntegro em `time_raw`. Não ocorre
em nenhum dos documentos atuais; a regra existe porque a especificação a exige.

**Falso negativo conhecido, e é o principal.** Um dígito trocado por outro
dígito — `07:00` lido como `01:00` — passa pela validação estrutural, porque
`1` é um dígito válido naquela posição. Não há como detectar isso sem uma
segunda fonte de leitura. É o ponto onde a solução menos merece confiança, e
entra na resposta da pergunta 3 do desafio.

**Onde a marcação aparece.** O `?` fica no `time_raw`; o `time_hhmm` das 4
batidas continua limpo (`23:00`), porque os dígitos foram lidos bem. Como a
planilha mostra `time_hhmm`, o `?` **não** aparece na célula. Consequência para
o bloco 2.3: o destaque amarelo de "qualquer `?` na linha" precisa ser
calculado sobre o **dado** da linha, incluindo `time_raw`, e não sobre o texto
da célula exibida. Sem isso, essas 4 linhas nunca seriam destacadas.

### 3.14 `time-card-04` não produz nenhum horário legível hoje

Medição feita durante o bloco 2.2, com a configuração atual (300 dpi, `psm 6`):
o scan real de cartão de papel devolve **zero** tokens com forma de horário.
O que sai são fragmentos como `(5520)`, `17083`, `5122226`.

Isto é registrado agora porque muda a expectativa sobre o bloco 2.5: o problema
de `time-card-04` não é de marcação de incerteza, é de OCR não conseguir ler o
documento. A estratégia de `?` não pode ser validada nele enquanto a extração
não produzir candidatos.

`payroll-04`, em contraste, lê valores monetários com confiança mínima de 93 e
nenhuma violação estrutural.

### 3.15 Destaque derivado do dado, não do texto da célula (bloco 2.3)

**O problema, descoberto no fim do bloco 2.2.** A especificação manda pintar de
amarelo a linha que tiver "algum `?`". A implementação óbvia — procurar `?` no
texto das células — **não funcionaria neste projeto**.

Caso real de `time-card-03`:

```
time_raw  = "23:00?"      <- a evidência de incerteza está aqui
time_hhmm = "23:00"       <- e é ISTO que a planilha mostra
```

Os dígitos foram lidos bem; só o marcador de sistema não. A célula da planilha
não contém `?` nenhum, e as 4 linhas afetadas nunca seriam destacadas.

**Decisão.** O destaque é derivado dos **dados estruturados** da linha,
varrendo todos os campos de texto — incluindo os `_raw`, que não aparecem na
planilha. A separação entre valor bruto, valor normalizado, estado de incerteza
e apresentação é preservada: nada é removido do raw para facilitar a exibição.

**Verificado:** as 4 linhas de `time-card-03` saem pintadas de amarelo no XLSX
mesmo com a célula mostrando `23:00`.

### 3.16 Regras de sequência: onde o alarme falso mora

As duas regras finas do README são fáceis de implementar errado, e as duas
falhas seriam silenciosas — alarme demais, que faz a pessoa parar de olhar.

**Dezembro → janeiro.** Comparar só o número do mês faria `12/2019 → 01/2020`
parecer uma quebra. `payroll-03` atravessa exatamente essa virada, e a planilha
dele sai **sem nenhum destaque**. Há teste separado garantindo que
`12/2019 → 01/2019` (sem somar o ano) continue sendo sinalizado.

**Competência ilegível não quebra a cadeia.** Uma página que não deu para ler
não pode gerar aviso nela nem na seguinte: comparam-se as próximas legíveis
entre si. Sem isso, uma leitura ruim produziria dois avisos em cascata sobre
dados corretos.

**Extensão registrada:** o README define a regra da ilegibilidade apenas para
competências. Apliquei o mesmo princípio às datas do cartão de ponto — uma data
que não dá para interpretar não quebra a cadeia. É uma decisão, não uma regra
oficial, e está registrada aqui porque havia outra resposta razoável (tratar a
data ilegível como quebra). Escolhi a que não gera alarme falso em cima de uma
leitura ruim.

**Data impossível.** `38/07/2019` tem forma de data e não existe no calendário.
O enunciado usa exatamente esse exemplo como erro de leitura, e ele quebra a
sequência por definição — então é sinalizado como data não sequencial. Não
ocorre nos documentos atuais; a regra existe porque a especificação a cita.

### 3.17 Aviso não altera o documento transcrito

Nenhuma função de `warnings_service` modifica o `value`. `29/10/2012` continua
com **uma** batida na saída — o sistema sinaliza, não completa. As 4 batidas
recuperadas no bloco 2.2 continuam presentes depois deste bloco, com teste de
regressão travando a contagem em 826.

### 3.18 Como a interface recebe os avisos (bloco 2.4)

**O problema.** O README exige que a tabela editável siga "as colunas da
planilha do tipo correspondente" e mostre os problemas "nas mesmas cores da
planilha", com o motivo legível. Ou seja: a tela e o arquivo baixado precisam
ser a mesma coisa.

**Alternativas consideradas.**

1. **Recalcular no JavaScript.** O frontend leria o `value` do GET e
   reimplementaria as colunas da planilha e as quatro regras de aviso.
   Rejeitada: duplica regra de negócio, e as duas implementações divergiriam na
   primeira mudança. Pior ainda no caso da incerteza — o JS teria que saber que
   precisa olhar `time_raw`, e não o valor exibido.

2. **Acrescentar os avisos ao GET obrigatório.** Rejeitada de imediato: o
   contrato é literal e avaliado automaticamente, e o README diz que os avisos
   **não são campo do JSON**.

3. **Endpoint auxiliar (adotada).** `GET /api/transcricoes/{id}/revisao`
   devolve a projeção pronta: colunas da planilha, valor de cada célula,
   severidade da linha e motivos legíveis.

**O caminho de cada célula.** A planilha é uma projeção do JSON — a coluna
`Entrada 2` do dia 5 é `pages.0.days.4.punches.2.time_hhmm`. O endpoint devolve
esse caminho junto com o valor, e o JavaScript só aplica `caminho → valor` num
objeto antes do PUT. Isso é genérico: o script não sabe distinguir cartão de
ponto de holerite.

Célula sem campo correspondente (verba que não existe naquela página, par de
batidas que o dia não tem) vem com caminho vazio e é somente leitura.

**Segundo endpoint auxiliar.** `GET /api/transcricoes/{id}/arquivo` serve o PDF
original `inline`, para o requisito de "PDF visível ao lado da tabela". O nome
exposto é derivado do id — o nome original do upload nunca foi guardado.

**Ambos são auxiliares e não substituem nenhum dos cinco endpoints
obrigatórios**, que continuam inalterados.

**Bootstrap versionado, não via CDN.** O arquivo está em `app/static/`. A
aplicação precisa funcionar dentro do `docker compose up` sem depender de rede
externa, e a página é a demonstração do produto.

### 3.19 Onde a interface deliberadamente não vai

- **Não adiciona batida.** Só é editável a célula que corresponde a um campo
  existente. Corrigir um dia com batida ímpar acrescentando a batida que falta
  exigiria mexer na estrutura do JSON pela tela, e isso ficou de fora — a
  interface é de revisão, não de composição.
- **Não corrige nada sozinha.** Nenhum valor é ajustado automaticamente; a
  tela sinaliza e deixa a pessoa decidir.
- **Não recalcula aviso após a edição.** Depois de cada PUT ela recarrega
  `/revisao`, então quem reavalia continua sendo o backend.

### 3.20 `time-card-04`: investigação de OCR e decisão de NÃO suportar (bloco 2.5)

**O documento.** Cartão de ponto de papel, fotografado. Página de 268×354 pt,
imagem embutida de 1116×1474 px. Marcações feitas por relógio de ponto
matricial, algumas em vermelho desbotado, com o mês escrito à mão.

**Causa medida.** A 300 dpi o render já iguala a resolução da imagem de origem.
Renderizar acima disso amplia sem acrescentar detalhe — não há informação nova
a recuperar.

**Alternativas testadas — 19 combinações.** Métrica: quantos tokens `HH:MM` o
OCR devolve na página 1. Verdade de campo por leitura visual: 8 linhas com 6
marcações cada, **~48 horários**.

| Variante | psm | horários |
|---|---|---|
| render 300 dpi | 6 / 4 / 12 | 0 |
| render 300 dpi | 11 | 1 (`9:20`) |
| 300 dpi cinza | 6 | 1 (`42:62`) |
| 300 dpi autocontraste | 6 / 11 | 1 / 0 |
| 300 dpi binarizada | 6 / 11 | 0 |
| 300 dpi binarizada + whitelist `0-9:` | 11 | 0 |
| render 600 dpi | 6 / 4 / 11 / 12 | 0 |
| 600 dpi cinza / autocontraste / binarizada | 6 / 11 | 0 |

**Melhor resultado: 1 horário de ~48 — e ele é lixo** (`42:62` não é hora).

**Alternativas de saída consideradas:**

1. **Emitir os dias com `punches: []`.** Rejeitada, e é a mais perigosa: a
   transcrição afirmaria que dias com 6 marcações não têm nenhuma. É
   exatamente o "valor errado com cara de certo" que o README chama de pior
   resultado possível.
2. **Emitir tudo marcado com `?`.** Rejeitada: o INSTRUCOES diz que "encher a
   saída de `?` para se proteger também não funciona — se você diz que não leu
   nada, você não transcreveu nada".
3. **Serviço de OCR em nuvem.** Fora do orçamento e exigiria credencial, o que
   conflita com "nenhum segredo no repositório".
4. **Não suportar (adotada).** Nenhum parser reconhece o documento, e o
   pipeline responde `status: "erro"` com mensagem legível.

A opção 4 é o comportamento que o próprio README recomenda: "responder 'não sei
ler este documento' é melhor que devolver lixo". Verificado: os seis parsers
devolvem score `0.0` para este documento.

**Onde a solução não merece confiança:** este é o principal item. Um quarto dos
cartões de ponto oficiais não é transcrito. Um produto real precisaria de OCR
especializado em dígitos matriciais ou de um serviço de nuvem.

### 3.21 `psm 4` melhoraria um documento e quebraria outro

Ao investigar a truncagem de rótulo do `payroll-04`, `--psm 4` recuperou 5
rótulos que o `psm 6` perde. Antes de trocar o padrão global, a mudança foi
medida nos outros documentos OCR:

| Documento | psm 6 | psm 4 |
|---|---|---|
| `time-card-03` | 56 dias, 158 batidas | **46 dias, 126 batidas** |
| `time-card-02` | equivalente | equivalente |
| `payroll-04` | 0 rótulos certos | 5 rótulos certos |

Trocar globalmente custaria **10 dias e 32 batidas** no `time-card-03`. O padrão
`psm 6` foi mantido e a truncagem do `payroll-04` fica registrada como
limitação. Um mecanismo de `psm` por documento não foi criado: a extração
acontece antes da seleção do parser, e inverter essa ordem por causa de um
layout seria pagar caro em arquitetura por um ganho pequeno.

### 3.22 Decisões P2 resolvidas neste bloco

| Documento | Situação | Decisão | Alternativa descartada |
|---|---|---|---|
| `payroll-04` | duas vias idênticas por página | uma entrada por página, cortando na segunda via | duas entradas — duplicaria toda verba e toda base |
| `payroll-02` | dois blocos (`MÊS`/`ACERTO`), mesma competência | uma entrada por bloco, compartilhando o `page` | fundir — rótulos iguais nos dois blocos colidiriam e o valor do `ACERTO` seria perdido |
| `payroll-01` | várias competências por página | uma entrada por competência, compartilhando o `page` | é o precedente que o próprio README descreve |
| `time-card-02` | horários de intervalo | primeiro é `OUT` (saída para o intervalo), segundo é `IN` | alternância por posição — daria `IN` para a saída |

### 3.23 Três perdas silenciosas encontradas e corrigidas no bloco 2.5

Todas descobertas conferindo a saída contra o documento, não por teste que
falhou.

**1. `time-card-02`: dois dias sumindo.** Agosto saía com 30 dias e setembro
com 29. Causa: o OCR cola o dia no dia da semana (`18QUA`, `18SAB`) e o parser
exigia um token puramente numérico. Percebido ao conferir a contagem de dias
contra o calendário. Corrigido extraindo os dígitos do início do token.

**2. `time-card-02`: batidas em token colado.** O OCR às vezes junta os dois
horários do intervalo num só token (`09:52-16:07`). Cada ocorrência custava uma
batida. Corrigido separando o token pelos separadores antes de ler. Total do
documento: 362 → **372 batidas**.

**3. `payroll-02`: uma verba inteira desaparecendo.** A primeira versão
distinguia referência de rótulo pela presença de `/` — supondo que só
referências como `JULHO/18` teriam barra. A verba
`192 ATFC-AD.TEMP.FATORES/COMI` tem barra **no nome**: o nome virou referência,
o rótulo ficou vazio e a linha foi descartada. Percebido conferindo a lista de
verbas da página 1 contra o PDF: 9 na saída, 10 no documento.

Corrigido trocando a adivinhação pelo conteúdo por uma decisão **posicional** —
a referência é o token que cai na faixa da coluna `Base / Saldo / Benefício`.
Total do documento: 86 → **92 verbas**.

O padrão dos três é o mesmo, e vale registrar: heurística baseada em conteúdo
(`tem barra?`, `é só dígito?`) falha em documento real; posição de coluna e
estrutura são mais confiáveis.

### 3.24 Auditoria de segurança: três lacunas fechadas (bloco 27.2)

A revisão de segurança encontrou três coisas que a implementação prometia e não
cumpria. Nenhuma era exótica; todas eram consequência de ter otimizado para o
caminho feliz.

**1. Concorrência sem limite.** Nada impedia N documentos de entrarem em OCR ao
mesmo tempo. Medido: 6 uploads simultâneos de um documento de 19 s levaram
**189 s** no total — pior que se tivessem esperado em fila (~114 s), porque o
Tesseract já satura os núcleos disponíveis e a disputa só adiciona troca de
contexto. Pior ainda na EC2: com 512 MiB e 2 jobs, o OOM killer derrubou o
processo — reproduzido, não suposto.

Corrigido com um `BoundedSemaphore` adquirido **dentro** da tarefa de
background, não no request. O POST continua respondendo 202 na hora; o
excedente espera com `status: processando`. A fila é o próprio semáforo — não
há fila distribuída, e nem precisa haver.

**2. PII em repouso sem restrição.** Os PDFs enviados contêm nome, CPF,
matrícula e salário, e estavam sendo gravados com a máscara padrão do processo.
Agora o diretório é `0700`, cada PDF `0600` e o banco `0600`. O nome original
do upload nunca chega ao disco — o arquivo usa o id opaco da transcrição —, e
isso tem teste próprio
(`test_nome_original_do_upload_nunca_vai_para_o_disco`).

**3. Retenção que dependia de tráfego.** A limpeza só rodava a cada upload, o
que significa que uma instância parada guardava PII indefinidamente. Passou a
rodar também na inicialização. Continua sem agendador, e a limitação residual
está declarada no `SOLUCAO.md`: uma instância de pé por semanas sem nenhum
upload só limpa no próximo reinício.

A correção da lacuna 2 trouxe um bug próprio, registrado em 4.7 — é o erro mais
instrutivo do conjunto, porque o teste passava.

### 3.25 Deploy: a infraestrutura real mudou a arquitetura (bloco 27.3)

**O que foi planejado.** A primeira preparação de deploy usava Caddy como proxy
reverso, com HTTPS automático via Let's Encrypt, num compose de produção
próprio. A escolha se sustentava na medição de memória: 512 MB não comporta o
pico de 402 MB do OCR com folga, e 1 GiB comporta.

**O que a inspeção da infraestrutura mostrou.** A EC2 escolhida **já estava em
produção**, com:

- Amazon Linux 2023 (não Ubuntu, como o guia inicial supunha);
- **Nginx e Certbot instalados no host**, ocupando as portas 80 e 443;
- Nícia Track em `127.0.0.1:8000` com PostgreSQL 16;
- MOSTQI em `127.0.0.1:8001`, de um desafio técnico anterior;
- certificados válidos, gerenciados por Certbot.

**A decisão: não introduzir um segundo proxy reverso.** Caddy precisaria das
portas 80 e 443, que já servem duas aplicações. Rodar os dois é impossível sem
derrubar o que está no ar. Reaproveitar o Nginx existente é mais simples — um
proxy, uma renovação de certificado, nenhum risco para os vizinhos.

O `deploy/Caddyfile` foi removido em vez de mantido "por histórico": config de
uma arquitetura descartada envelhece mal e confunde quem lê. O histórico é este
registro.

**Diagnóstico da instância.** `t3.micro`, 2 vCPU, **~912 MiB de RAM**, EBS
20 GB. Com as três aplicações no ar, `MemAvailable` estava em **~298 MiB** —
menos que o pico de 402 MB de um único OCR. Consumo observado: Nícia ~101 MiB,
PostgreSQL ~41 MiB, MOSTQI ~67 MiB em repouso. **Nenhum container tinha limite
de memória.** CPU praticamente ociosa (load ~0,01, idle 99–100%), sem registro
de OOM no kernel, disco sem gargalo.

**O risco, explicitamente.** Subir o Quick Filler ali sem proteção poderia
levar o OOM killer do host a escolher a vítima — e o PostgreSQL é um alvo
provável, por ser o processo de maior RSS. O serviço de menor valor derrubaria
o de maior.

**Três medidas, todas reversíveis:**

1. **MOSTQI parado** (`docker stop`, container e imagem preservados). Liberou
   `MemAvailable` de ~298 para ~339 MiB. Reversível com `docker start`.
2. **2 GiB de swap** no EBS existente, persistido em `/etc/fstab`. Swap aqui é
   **amortecedor de pico, não substituto de RAM** — a intenção é absorver o
   momento do OCR, não rodar a aplicação em disco.
3. **`vm.swappiness` de 60 para 10**, persistido em
   `/etc/sysctl.d/99-swap.conf`, para o kernel preferir RAM física e recorrer
   à swap só sob pressão.

**Mais duas decisões no projeto:**

- `QF_MAX_PROCESSAMENTO_SIMULTANEO=1`, obrigatório e não negociável nesta
  instância;
- **limite de memória no container** (`mem_limit: 600m`,
  `memswap_limit: 1600m`), que os vizinhos não têm. Com ele, um estouro fica
  contido no cgroup do Quick Filler: quem morre é o serviço descartável, e a
  transcrição termina em `erro` — em vez de o kernel escolher o PostgreSQL.

**Porta 8002, publicada em loopback.** A 8001 está livre porque o MOSTQI foi
parado, mas ele pode voltar; ocupá-la criaria conflito silencioso. O prefixo
`127.0.0.1:` garante que só o Nginx local alcance a aplicação, de modo que todo
acesso externo passe por TLS.

> A justificativa original deste item afirmava que o bind em `0.0.0.0` faria o
> Docker "passar por cima do Security Group". **Isso está errado** e foi
> corrigido — ver o fim da seção 3.26. A decisão continua a mesma; só o motivo
> estava impreciso.

**Trade-offs assumidos.** Três aplicações numa `t3.micro` de 912 MiB é apertado.
Ganha-se custo zero adicional e nenhuma infraestrutura nova; paga-se com margem
estreita e com o Quick Filler dependendo de swap num pico. É aceitável **porque
o tráfego esperado é de demonstração**, não de produção real.

**Esta arquitetura NÃO está validada.** Ela só passa a estar depois de medir um
OCR real na instância: RAM antes e durante, `MemAvailable`, swap usada, CPU,
consumo por container, ausência de OOM, e o comportamento depois que o
processamento termina. O critério para abandoná-la e migrar para uma instância
de ~2 GiB está escrito em `deploy/README.md`.

### 3.26 Deploy executado: medições reais da EC2 (bloco 27.3)

O deploy foi realizado na EC2 compartilhada. Os números abaixo são **da
instância**, não do ambiente de desenvolvimento — a distinção importa, porque
as duas medições não coincidem.

**Publicado em:** `https://quickfiller.paulodev.net` · commit `e75493d`

#### Incidente: Buildx incompatível

O primeiro `docker compose up --build` falhou **antes de qualquer build**:

    compose build requires buildx 0.17.0 or later

A Amazon Linux 2023 entrega o Buildx **0.12.1** dentro do próprio pacote do
Docker (`docker-25.0.16-1.amzn2023.0.2.x86_64`), em
`/usr/libexec/docker/cli-plugins/`. Não há pacote separado no `dnf`, e o
Compose instalado (v5.3.0) exige 0.17.0+.

**Alternativa descartada:** atualizar ou trocar o Docker do sistema. Ele
sustenta Nícia, PostgreSQL e MOSTQI — mexer nele para publicar um desafio
técnico inverteria a prioridade entre o serviço crítico e o descartável.

**Solução adotada:** instalar o Buildx **apenas para o usuário**, em
`~/.docker/cli-plugins/docker-buildx` (v0.36.1). O plugin do usuário tem
precedência sobre o do sistema, o 0.12.1 original permanece intacto, e a
mudança é reversível apagando um arquivo. Nenhum serviço existente foi
reiniciado.

Build subsequente: **34 s**, sem falha de memória.

#### Baseline antes do OCR

| | |
|---|---|
| RAM | 912 MiB total · 439 usada · **313 disponível** |
| Swap em uso | 21,5 MiB |
| Quick Filler | 61,34 MiB / 600 |
| Nícia | 89,72 MiB |
| PostgreSQL | 36,95 MiB |
| Load | 0,04 / 0,10 / 0,05 |

#### Durante um OCR real, pela interface pública

Documento de 280 linhas, 4 marcadas como "precisam de atenção" — o mesmo
resultado obtido localmente, agora por HTTPS.

| | Observado |
|---|---|
| Quick Filler | **~459–466 MiB / 600** |
| CPU do container | ~115–143% |
| **RAM disponível no host** | **caiu a ~61–67 MiB** |
| **Swap em uso** | **subiu a ~315–325 MiB** |

Estes são os maiores valores vistos numa amostragem de 2 s — **não
necessariamente o pico absoluto**.

Comparação com o ambiente de desenvolvimento: localmente, o mesmo container com
o mesmo limite chegou a 507,4 MiB. A EC2 observou 459–466 MiB. Mesma ordem de
grandeza, ambos abaixo do limite de 600 MiB — a estimativa local se sustentou.

#### Depois do OCR

RAM voltou a 305 MiB disponíveis, swap a ~21 MiB, Quick Filler a ~61 MiB.
`OOMKilled=false`, `RestartCount=0`, **nenhum registro de OOM no kernel**,
Nícia e PostgreSQL ativos. Load 0,15 / 0,08 / 0,04.

O swap voltou ao patamar de repouso, o que confirma que ele funcionou como
**amortecedor de pico** e não como memória de trabalho permanente.

#### HTTPS

Certbot emitiu e implantou o certificado (`--nginx`), com renovação automática
configurada. Validade até 2026-11-11. `http://` responde **301** para
`https://`. `nginx -t` passou antes e depois. Os arquivos de configuração da
Nícia e do MOSTQI não foram tocados.

#### Conclusão de capacidade — agora com evidência real

A configuração (t3.micro · 2 GiB swap · `swappiness=10` · MOSTQI parado ·
limite de 600 MiB · concorrência 1) **concluiu um OCR real sem OOM, sem
reinício e sem queda observada da Nícia ou do PostgreSQL**.

**Mas a margem é estreita.** A RAM disponível do host caiu para ~60–70 MiB e a
swap passou de 300 MiB durante o processamento.

Portanto:

- **adequada** para o cenário atual: desafio, demonstração, tráfego baixo;
- **não adequada** para concorrência real ou vários usuários simultâneos;
- **não aumentar** `QF_MAX_PROCESSAMENTO_SIMULTANEO` acima de 1 nesta EC2;
- swap **não** é substituto permanente de RAM — se ela passar a ser usada de
  forma sustentada, o dimensionamento está errado, não resolvido;
- havendo crescimento de tráfego ou impacto nos outros serviços, migrar o
  Quick Filler para instância com mais RAM ou infraestrutura separada.

#### Correção de uma imprecisão minha

O comentário original no `docker-compose.prod.yml` afirmava que publicar em
`0.0.0.0` faria o Docker "passar por cima do Security Group". **Está errado:**
o Security Group é aplicado fora da instância, no nível da ENI, e continua
valendo independentemente do bind.

O que o Docker de fato contorna são regras de firewall configuradas **no
host** (firewalld/iptables na cadeia INPUT), porque publica via DNAT. O bind em
`127.0.0.1` continua sendo a decisão certa — por reduzir superfície de
exposição e garantir que todo acesso externo passe pelo proxy, ou seja, por
TLS. Só a justificativa estava imprecisa, e foi corrigida.

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

### 4.7 Um bug dentro da própria correção de segurança — e o teste passava

**O que aconteceu:** ao fechar a lacuna de permissões (3.24), a correção
proposta foi criar o diretório de PII já com o modo certo:

```python
self.storage_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
```

Parece correto e tem teste verde. **Não funciona.** O argumento `mode` do
`mkdir` só se aplica quando o diretório é **criado**; com `exist_ok=True` sobre
um diretório que já existe, a chamada é um no-op silencioso e as permissões
antigas permanecem. Em produção o volume `/data` já existia desde o primeiro
deploy — então o diretório seguia `0755`, expondo PII, enquanto a suíte
afirmava que estava tudo certo.

**Como foi percebido:** não pelo teste, que passava. O teste criava o diretório
do zero em `tmp_path`, que é exatamente o único caso em que o `mode` do `mkdir`
funciona. Apareceu ao conferir as permissões **reais** dentro do container, com
`ls -ld`, em vez de aceitar o verde da suíte.

**Correção:** `chmod` explícito, aplicado sempre, separado da criação:

```python
self.storage_dir.mkdir(parents=True, exist_ok=True)
self.storage_dir.chmod(0o700)
```

E, principalmente, um teste de regressão que chama `ensure_directories()`
**duas vezes** — a segunda sobre um diretório já existente, que é o caso real:
`test_permissoes_sobrevivem_a_diretorio_ja_existente`.

**Por que é o erro mais instrutivo da lista:** os outros produziram saída
errada, visível a quem conferisse. Este produziu **verde**. O teste não estava
errado no que afirmava — estava testando uma situação que nunca acontece em
produção, e por isso a garantia que ele dava era falsa. Um teste que exercita o
caminho fácil é pior que nenhum teste, porque compra confiança sem entregar
cobertura.

---

## 5. O que foi reescrito à mão, e por quê

**Resposta direta: nenhum trecho de código foi reescrito à mão.**

Todo o código desta entrega foi produzido com auxílio de IA. Não há nesta
solução uma função, um parser ou um teste que eu tenha digitado manualmente
para substituir o que o agente escreveu. Dizer o contrário renderia uma seção
mais bonita, e seria mentira — num desafio cujo critério central é justamente
não apresentar como certo aquilo de que não se tem certeza.

### O que eu fiz, então

O trabalho manual existiu, mas não foi digitar código. Foi:

- **revisar** cada implementação gerada antes de aceitá-la;
- **conduzir o desenvolvimento por etapas**, fechando um bloco por vez em vez
  de pedir a solução inteira de uma só vez;
- **validar o comportamento do sistema** contra os PDFs reais, em vez de
  confiar na descrição do que o código deveria fazer;
- **analisar os resultados dos testes** — inclusive os que passavam;
- **solicitar correções e ajustes** quando o resultado não se sustentava;
- **decidir se cada etapa estava adequada** antes de seguir para a próxima.

### Por que isso não é um detalhe de processo

Porque foi essa camada — e não a escrita de código — que pegou os erros deste
documento. Vale conferir contra a seção 4:

| O que o agente entregou | O que a revisão pegou |
|---|---|
| Um filtro `confiança < 30 → descartar`, plausível e nunca medido (4.4) | Exigir a medição antes de aceitar mostrou que ele apagava 4 batidas corretas em silêncio. O filtro foi removido inteiro. |
| Um teste verde para a correção de permissões (4.7) | Conferir as permissões **reais** dentro do container, em vez de aceitar o verde, revelou que a correção era um no-op e a PII seguia exposta. |
| Um parser de `payroll-02` que "funcionava" (3.23) | Conferir a saída contra o PDF página a página mostrou 9 verbas onde o documento tinha 10. |
| A especificação lida numa versão traduzida e resumida (4.1) | Desconfiar da fonte e buscar o arquivo cru recuperou requisitos literais que tinham sumido na tradução. |

O padrão é o mesmo nos quatro: **nenhum apareceu como erro**. Não houve exceção,
teste vermelho ou log de falha. Todos apareceram porque a saída foi conferida
contra o documento real, e porque medição foi exigida no lugar de plausibilidade.

Se há uma habilidade demonstrada nesta entrega, não é a de escrever à mão as
~9 mil linhas que ela tem (5.005 na aplicação, 3.497 em testes, 493 na
interface) — é a de não aceitar as que estavam erradas. Foi também a
percepção de que `date_raw` era ambíguo o suficiente para ser levado à Quick
Filler (3.8) em vez de resolvido por suposição, e a de que `time-card-04` devia
falhar explicitamente (3.20), mesmo custando um documento na nota de precisão.

### O risco que isso deixa

Registrado por honestidade, e desenvolvido em 6.3: revisão pega o que se sabe
conferir. As perdas silenciosas foram encontradas porque havia um PDF ao lado
para comparar. Num documento que eu não pudesse conferir contra a fonte, esse
método não teria funcionado — e é exatamente por isso que a aplicação foi
construída para marcar `?` e destacar linha suspeita, em vez de depender de
alguém conferir tudo.

---

## 6. Respostas às perguntas do desafio

### 6.1 Três decisões em que havia mais de uma resposta razoável

Havia decisões de infraestrutura com duas saídas defensáveis — SQLite contra
PostgreSQL (3.1), `BackgroundTasks` contra Celery (3.3) — mas nelas o critério
foi quase mecânico: o `docker compose up` é requisito duro, e cada serviço a
mais custa contra ele. As três abaixo foram mais difíceis porque **nenhuma
tinha um critério externo para resolver a disputa.**

**1. Marcar incerteza por validação estrutural, não pela confiança do OCR
(3.13).**

A resposta "óbvia" é usar a confiança que o Tesseract já entrega: existe, é
barata, e todo mundo faria. Foi o que o agente propôs, com um corte em 30.

Escolhi o caminho oposto — validar a **forma** do campo, posição por posição —
depois de medir. Em `time-card-03`, sobre 822 horários lidos corretamente, a
confiança mínima era 0, a mediana 91, e **47 estavam certos com confiança
abaixo de 30**. Os 4 tokens realmente errados tinham confiança 25, 41, 44 e 53
— dentro da faixa dos corretos. E há o contraexemplo direto: `Sai1` lido
**errado** como `Sail`, com confiança **95**.

Por que essa: o corte por confiança falha nas duas direções ao mesmo tempo —
descarta dado bom e deixa passar dado ruim. A validação estrutural erra menos
porque pergunta algo que o documento pode responder ("o segundo caractere de um
horário pode ser uma letra?") em vez de algo que só o motor de OCR opina.

O custo está assumido: dígito trocado por dígito passa. Está em 6.3.

**2. Compor ou não a data completa em `date_raw` (3.8).**

Três dos quatro cartões imprimem só o dia na linha, com a competência no
cabeçalho. `date_raw` é definido como "a data exatamente como está impressa" —
o que, lido ao pé da letra, significa gravar `01` e descartar a única
informação que torna a linha utilizável numa planilha.

As duas leituras eram razoáveis, e a escolha mudava toda linha de todo cartão
de ponto. **Levei a dúvida à Quick Filler em vez de assumir** — o README diz
que perguntar é comportamento desejado. A resposta aceitou as duas e indicou
compor quando a associação for segura, sem completar sob ambiguidade.

Por que essa: era a decisão de maior alcance do projeto e a que eu tinha menos
autoridade para tomar sozinho. Custou uma mensagem.

**3. `time-card-04`: falhar explicitamente em vez de entregar algo (3.20).**

Depois de 19 combinações de DPI, modo de segmentação e pré-processamento, o
melhor resultado recuperou 1 de ~48 horários — e era lixo (`42:62`). Havia três
saídas, todas defensáveis:

| Saída | Por que foi rejeitada |
|---|---|
| Emitir os dias com `punches: []` | Afirma que dias com 6 marcações não têm nenhuma. É o "valor errado com cara de certo" que o enunciado chama de pior resultado possível. |
| Emitir tudo com `?` | Não transcreveu nada, e o INSTRUCOES é explícito: "se você diz que não leu nada, você não transcreveu nada". |
| `status: "erro"` com mensagem legível | **Escolhida.** |

Por que essa: é a única que não mente. Custa 1 dos 8 documentos na nota de
precisão, e eu preferi esse custo a contaminar a planilha. O enunciado trata
"não sei ler este documento" como resposta aceitável — inclusive a lista como
bônus.

### 6.2 O que quebra primeiro em produção?

**A memória, sob dois OCRs simultâneos.** Não é hipótese: está medido.

A aplicação roda numa `t3.micro` com ~912 MiB, **compartilhada com outra
aplicação em produção e um PostgreSQL**. Durante um OCR real, medido na própria
EC2 (3.26): a RAM disponível caiu de 313 MiB para ~61–67 MiB, o swap subiu a
~315–325 MiB e o container chegou a ~459–466 MiB do limite de 600.

Isso é **um** documento. A margem que sobra não comporta o segundo. Por isso
`QF_MAX_PROCESSAMENTO_SIMULTANEO=1` em produção — e essa é exatamente a
confissão: a concorrência não está resolvida, está **desligada**. O segundo
usuário não recebe erro; ele espera, com `status: processando`, o tempo inteiro
do documento da frente. Num OCR de 28 s, com uma fila de cinco, o último espera
mais de dois minutos sem nenhum sinal de que está em fila.

Antes de chegar a `1`, o comportamento sem limite algum foi medido: 6 uploads
simultâneos de um documento de 19 s levaram 189 s no total — **pior que em
fila**. E com 512 MiB e 2 jobs, o OOM killer derrubou o processo. Os dois casos
foram reproduzidos, não imaginados.

Então a ordem realista de falha é: **capacidade primeiro** (fila visível ao
usuário, e uma máquina que não tem para onde crescer), **layout desconhecido em
segundo** (termina em `erro` explicado — comportamento correto, mas é um
documento não transcrito), **retenção em terceiro** (só roda no start e a cada
upload; uma instância parada por semanas só limpa no reinício).

O caminho de correção não é misterioso — é uma instância com ~2 GiB e um worker
de verdade. É decisão de custo, não de arquitetura, e está registrada em
`deploy/README.md` como critério de migração.

### 6.3 Onde você não confia no que entregou?

**Nos dígitos que o OCR trocou por outros dígitos.** É o furo conhecido da
estratégia de incerteza, e o mais grave. `07:00` lido como `01:00` tem forma
perfeita de horário: passa pela validação estrutural sem marca nenhuma, e sai
na planilha com cara de dado bom. O caso real está no `payroll-04`, que teve o
ano `2019` lido como `2016` em três páginas. Ali o aviso de mês não sequencial
pegou — mas pegou por sorte estrutural, porque quebrou uma sequência. **Um
horário trocado no meio de um cartão de ponto não quebra sequência nenhuma.**
Não há segunda fonte de leitura para cruzar, e sem isso não é detectável.

**Na generalização dos parsers.** Cada um dos 7 foi construído contra
exatamente **um** documento. As armadilhas que eu conheço estão cobertas por
teste, mas "conheço" aqui significa "encontrei nesses 8 PDFs". O INSTRUCOES
lista "ajustar o código ao PDF de exemplo" como erro que derruba entregas, e a
defesa adotada é estrutural — colunas localizadas pelo cabeçalho, nunca
coordenada fixa; nenhum número de páginas ou data gravado no código. Isso é
melhor que amarrar em x/y, mas **não é o mesmo que ter validado em documentos
que eu nunca vi**. Um layout novo do mesmo emissor, com uma coluna a mais, é o
teste que essa entrega não tem.

**Na cobertura do que eu não sei que não sei.** As três perdas silenciosas do
bloco 2.5 (3.23) — dias e verbas que sumiam sem erro, sem log, sem teste
falhando — não apareceram por teste. Apareceram porque a saída foi conferida
contra o PDF real, linha a linha. Elas existiam havia commits. Isso me diz que
o método que as encontrou é conferência manual, e conferência manual não escala
para além dos 8 documentos que eu conferi. É razoável supor que exista uma
quarta que eu ainda não contei.

**Onde eu confio:** na separação `fields`/`bases`, verificada documento a
documento; no contrato HTTP, validado contra os exemplos literais do enunciado;
em que nada é descartado em silêncio no caminho do OCR, que é uma regressão
travada por teste; e em que o sistema falha alto quando não sabe ler, em vez de
inventar.

---

## 7. Estado atual da implementação

**Entrega fechada.** As três fases foram concluídas e commitadas; o que segue é
o registro de cada bloco e as medições que o fecharam.

### Fase 1 — fundação

| Bloco | Estado |
|---|---|
| 1/4 — Fundação, Docker, Tesseract, `/healthz` | concluído e validado |
| 2/4 — Contrato HTTP, persistência, processamento assíncrono | concluído e validado |
| 3/4 — Extração (`ExtractedPage`: texto nativo + OCR) | concluído e validado |
| 4/4 — Registry + primeiro parser real (SIPON) | concluído e validado |

### Fase 2 — cobertura e revisão

| Bloco | Entrega | Estado |
|---|---|---|
| 2.1 | `payroll-03` + `time-card-03` — cobertura dos dois tipos | concluído e validado |
| 2.2 | Incerteza `?` por caractere | concluído e validado |
| 2.3 | Avisos derivados + destaques na planilha | concluído e validado |
| 2.4 | Interface de revisão | concluído e validado |
| 2.5 | Layouts restantes | concluído — 7 de 8 PDFs suportados |

### Fase 3 — operação, publicação e entrega

| Bloco | Entrega | Estado |
|---|---|---|
| 27.1 | Validação do Docker em ambiente limpo | concluído |
| 27.2 | Auditoria de segurança — três lacunas fechadas (3.24) | concluído |
| 27.3 | Deploy real em EC2 com Nginx + HTTPS (3.25, 3.26) | concluído |
| 27.4 | CI/CD | **pulado deliberadamente** — é diferencial, não requisito |
| 27.5 | `README.md` e `SOLUCAO.md` | concluído |
| 27.6 | Planilhas dos 8 PDFs de `exemplos/` | concluído — 7 geram planilha |
| 27.7 | Revisão final da entrega | concluído |

Cobertura de layouts: **7 de 8**. O único não suportado é `time-card-04`, e a
investigação que sustenta essa decisão está na seção 3.20.

Medição do bloco 2.1, contra os PDFs reais:

- `payroll-03`: 5 páginas, competências 10/2019 a 02/2020 (atravessa a virada
  de ano), 44 verbas, 45 bases, zero vazamento de base para `fields`;
- `time-card-03`: 5 páginas via OCR, 280 dias, 822 batidas, datas contínuas de
  16/12/2019 a 20/09/2020 sem lacuna nem duplicata.

> As 822 batidas acima são a medição **do bloco 2.1**, e ficaram para trás: o
> bloco 2.2 removeu o descarte por confiança e recuperou 4 batidas que estavam
> sendo perdidas em silêncio. O número final é **826**, que é o que aparece no
> `SOLUCAO.md` e o que o teste de regressão trava.

Observação operacional: `time-card-03` leva ~28 s para processar por HTTP, por
causa do OCR. O `status` sai de `processando` e chega em `concluido` sem
bloquear a requisição — é a primeira validação prática de que a aplicação
"sobrevive a um documento demorado", que é critério explícito de arquitetura.

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

Regra adotada:

1. associação segura → `date_raw` recebe a data completa;
2. associação insegura → preservar só o valor disponível na linha;
3. nunca inferir mês/ano sob ambiguidade — esta regra tem precedência.

Consequência prática: `time-card-01` e `time-card-02` compõem a data;
`time-card-04` não compõe, porque o mês é manuscrito ilegível numa página e
está em branco na outra.

Vale registrar o processo em si: perguntar em vez de assumir custou uma
mensagem e eliminou o risco de implementar uma interpretação errada de um campo
que aparece em toda linha de todo cartão de ponto.
