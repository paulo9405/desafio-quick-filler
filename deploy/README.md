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

**Publicado e validado em produção.** As medições reais da instância estão em
`PROCESSO.md`, seção 3.26.

## Por que não Caddy

A preparação anterior usava Caddy com HTTPS automático. **Foi descartada**: o
Caddy precisaria das portas 80 e 443, que o Nginx do host já ocupa servindo
Nícia e MOSTQI. Rodar os dois é impossível sem derrubar o que já está no ar.

Reaproveitar o Nginx é mais simples e mais seguro: um proxy só, uma renovação
de certificado só, e nenhum risco para as aplicações existentes. O histórico da
decisão está em `PROCESSO.md`.

## Por que a porta 8002

A 8001 ficou livre porque o container do MOSTQI foi parado — mas ele continua
existindo e pode ser religado. Ocupar a porta dele criaria um conflito
silencioso nesse dia. A 8002 é nova e mantém a numeração legível.

A publicação é **em loopback** (`127.0.0.1:8002:8000`): só o Nginx local
alcança a aplicação, então todo acesso externo passa pelo proxy — ou seja, por
TLS.

O Security Group da AWS continua valendo mesmo com bind em `0.0.0.0`, porque é
aplicado fora da instância, no nível da ENI. O que o loopback acrescenta é
reduzir a superfície de exposição: o Docker publica portas via DNAT, e essas
regras não respeitam firewall configurado no host (`firewalld`/`iptables`
INPUT). O SG protege; o loopback garante.

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

### 3. Buildx — necessário na Amazon Linux 2023

O primeiro `--build` falha antes de compilar qualquer coisa:

```
compose build requires buildx 0.17.0 or later
```

A AL2023 entrega o Buildx **0.12.1** dentro do próprio pacote do Docker
(`/usr/libexec/docker/cli-plugins/`), e não há pacote separado no `dnf`.

**Não atualize o Docker do sistema** — ele sustenta as outras aplicações da
máquina. Instale o Buildx apenas para o usuário; o plugin do usuário tem
precedência e a mudança é reversível apagando o arquivo:

```bash
mkdir -p ~/.docker/cli-plugins
curl -sSL -o ~/.docker/cli-plugins/docker-buildx \
  https://github.com/docker/buildx/releases/latest/download/buildx-v0.36.1.linux-amd64
chmod +x ~/.docker/cli-plugins/docker-buildx
docker buildx version    # deve mostrar v0.36.1
```

### 4. Subir a aplicação (ainda sem Nginx)

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Build medido na instância: **~34 s**, sem falha de memória.

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

### 5. Nginx

```bash
sudo cp deploy/nginx-quickfiller.conf /etc/nginx/conf.d/quickfiller.conf
sudo nginx -t          # precisa passar antes do reload
sudo systemctl reload nginx
```

`reload` não derruba conexões — Nícia continua servindo.

### 6. Certificado

```bash
sudo certbot --nginx -d quickfiller.paulodev.net
```

O Certbot edita `quickfiller.conf` acrescentando o bloco 443 e o
redirecionamento. **Não toca nos outros arquivos.**

Depois disso, religar o proxy do Cloudflare, se desejado.

### 7. Validação

```bash
curl -i https://quickfiller.paulodev.net/healthz
curl -I  http://quickfiller.paulodev.net/            # 301/308 → https
```

---

## Capacidade — medido em produção

Um OCR real foi executado pela interface pública. Resultado:

| Momento | RAM disponível | Swap em uso | Quick Filler |
|---|---|---|---|
| Antes | 313 MiB | 21,5 MiB | 61 MiB |
| **Durante o OCR** | **~61–67 MiB** | **~315–325 MiB** | **~459–466 MiB / 600** |
| Depois | 305 MiB | ~21 MiB | 61 MiB |

Sem OOM, sem reinício, Nícia e PostgreSQL ativos o tempo todo. O swap voltou ao
patamar de repouso — funcionou como amortecedor de pico, não como memória de
trabalho.

**A margem é estreita.** Adequada para demonstração e tráfego baixo; **não**
para concorrência real. Não aumente `QF_MAX_PROCESSAMENTO_SIMULTANEO` nesta
instância.

### Como repetir a medição

Antes de enviar o documento:

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

### Critério para migrar para instância maior

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
