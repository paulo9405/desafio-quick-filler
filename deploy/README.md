# Deploy — EC2 existente com Nginx

A aplicação é publicada numa EC2 que **já está em produção** com outras
aplicações. O deploy se encaixa na infraestrutura existente em vez de trazer a
sua própria.

```
Internet → HTTPS → Nginx (host) ─┬─ 127.0.0.1:8000 → Nícia Track
                                 ├─ 127.0.0.1:8001 → MOSTQI (parado)
                                 └─ 127.0.0.1:8002 → Quick Filler
```

| | |
|---|---|
| Instância | `t3.micro`, us-east-2, Amazon Linux 2023 |
| Recursos | 2 vCPU · ~912 MiB RAM · EBS 20 GB |
| Swap | 2 GiB, `vm.swappiness=10` |
| TLS | Nginx + Certbot **já instalados no host** |
| Domínio | `quickfiller.paulodev.net` (DNS no Cloudflare) |

## Por que não Caddy

A preparação anterior usava Caddy com HTTPS automático. **Foi descartada**: o
Caddy precisaria das portas 80 e 443, que o Nginx do host já ocupa servindo
Nícia e MOSTQI. Rodar os dois é impossível sem derrubar o que já está no ar.

Reaproveitar o Nginx é mais simples e mais seguro: um proxy só, uma renovação
de certificado só, e nenhum risco para as aplicações existentes. O histórico da
decisão está em `docs/PROCESSO.md`.

## Por que a porta 8002

A 8001 ficou livre porque o container do MOSTQI foi parado — mas ele continua
existindo e pode ser religado. Ocupar a porta dele criaria um conflito
silencioso nesse dia. A 8002 é nova e mantém a numeração legível.

A publicação é **em loopback** (`127.0.0.1:8002:8000`). Sem o prefixo, o Docker
publicaria em `0.0.0.0` e criaria uma regra de DNAT que passa por cima do
Security Group — a aplicação ficaria acessível pela internet em HTTP puro,
contornando o TLS.

---

## Sequência do deploy

Cada passo é reversível e nenhum toca nas aplicações existentes.

### 1. DNS (Cloudflare)

Registro `A`: `quickfiller` → IP público da instância.

> **Atenção ao proxy do Cloudflare (nuvem laranja).** Com ele ligado, o
> Certbot no modo `--nginx` falha, porque o desafio HTTP-01 não chega ao
> servidor. Deixe **DNS only** (nuvem cinza) até o certificado ser emitido.

Confirme antes de seguir:

```bash
dig +short quickfiller.paulodev.net
```

### 2. Código

```bash
git clone https://github.com/paulo9405/desafio-quick-filler.git
cd desafio-quick-filler
```

### 3. Subir a aplicação (ainda sem Nginx)

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

O build leva alguns minutos e é a etapa mais pesada em memória — é para ela
que o swap existe.

Validar antes de expor:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8002/healthz   # 200
curl -s http://127.0.0.1:8002/healthz                                     # {"status":"ok"}
```

Confirmar que os vizinhos não foram afetados:

```bash
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
free -m
```

### 4. Nginx

```bash
sudo cp deploy/nginx-quickfiller.conf /etc/nginx/conf.d/quickfiller.conf
sudo nginx -t          # precisa passar antes do reload
sudo systemctl reload nginx
```

`reload` não derruba conexões — Nícia continua servindo.

### 5. Certificado

```bash
sudo certbot --nginx -d quickfiller.paulodev.net
```

O Certbot edita `quickfiller.conf` acrescentando o bloco 443 e o
redirecionamento. **Não toca nos outros arquivos.**

Depois disso, religar o proxy do Cloudflare, se desejado.

### 6. Validação

```bash
curl -i https://quickfiller.paulodev.net/healthz
curl -I  http://quickfiller.paulodev.net/            # 301/308 → https
```

---

## Monitoramento durante o primeiro OCR

A arquitetura **ainda não está validada**. Ela só passa a estar depois de medir
um OCR real na instância. Antes de enviar o documento:

```bash
free -m; cat /proc/pressure/memory
docker stats --no-stream
```

Durante o processamento, num segundo terminal:

```bash
watch -n 2 'free -m; echo; docker stats --no-stream --format \
  "table {{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}"'
```

Depois:

```bash
dmesg -T | grep -i -E 'oom|killed process' | tail   # precisa sair vazio
docker ps --format 'table {{.Names}}\t{{.Status}}'  # Nícia e PostgreSQL de pé
```

### Critério para abandonar esta arquitetura

Migrar para uma instância dedicada com ~2 GiB se qualquer um ocorrer:

- registro de OOM no `dmesg`;
- Nícia ou PostgreSQL reiniciados ou degradados;
- swap em uso sustentado depois do fim do OCR;
- OCR levando muito mais que os ~37 s medidos em 1 vCPU;
- container do Quick Filler morto pelo limite de memória de forma recorrente.

---

## Operação

```bash
docker compose -f docker-compose.prod.yml logs -f app     # logs, sem PII
docker compose -f docker-compose.prod.yml restart app
docker compose -f docker-compose.prod.yml up -d --build   # atualizar
```

Dados no volume `qf-data` sobre o EBS: sobrevivem a `down`/`up` e a reinício da
instância. `down -v` apaga.

## O que NÃO foi tocado

- Nícia Track e PostgreSQL — intocados;
- `nicia-track.conf` e `mostqi.conf` — intocados;
- container e imagem do MOSTQI — **parados, não removidos**, reversível com
  `docker start mostqi-rpa` (exige que a porta 8001 continue livre — por isso o
  Quick Filler usa a 8002).
