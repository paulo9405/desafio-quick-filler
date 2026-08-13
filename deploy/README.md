# Deploy em AWS EC2

Passo a passo para publicar a aplicação com HTTPS. As etapas marcadas
**[VOCÊ]** exigem acesso à sua conta AWS e ao seu DNS.

## Por que EC2, e por que 1 GB

A decisão veio de medição, não de preferência:

| Recursos | 1 documento OCR | 2 simultâneos |
|---|---|---|
| 1 vCPU / 512 MB | 36,8 s | **morto pelo OOM killer** |
| 1 vCPU / 1 GB | ~37 s | 87 s, sem erro |

Pico de memória de um documento OCR: **402 MB**. Monitorando o servidor com
512 MB, o container chegou a 511,9 MiB de 512 MiB — sem folga. Por isso 1 GB
e concorrência 1.

A EC2 ainda elimina o cold start, o que importa para a avaliação e para a
sessão técnica ao vivo, e o EBS resolve a persistência sem configuração extra.

---

## 1. [VOCÊ] Instância

- **Tipo:** `t3.micro` (2 vCPU burstable, 1 GB)
- **Imagem:** Ubuntu Server 24.04 LTS
- **Disco:** 20 GB gp3 (a imagem tem ~316 MB; o resto é folga para PDFs e banco)

## 2. [VOCÊ] Security Group

| Porta | Origem | Motivo |
|---|---|---|
| 22 | **seu IP apenas** | SSH |
| 80 | 0.0.0.0/0 | desafio HTTP-01 do Let's Encrypt e redirecionamento |
| 443 | 0.0.0.0/0 | HTTPS |

**Não abrir a 8000.** A aplicação não publica porta no host — só o Caddy
escuta. Abrir 8000 permitiria acesso em HTTP puro, contornando o TLS.

## 3. [VOCÊ] Domínio

O Let's Encrypt não emite certificado para IP. É preciso um nome apontando
para o IP público da instância.

- **Domínio próprio:** registro `A` → IP da instância.
- **Sem domínio:** [DuckDNS](https://www.duckdns.org) resolve em ~2 min —
  criar um subdomínio e apontar para o IP.

Confirme antes de seguir:

```bash
dig +short SEU.DOMINIO      # precisa devolver o IP da instância
```

## 4. Docker na instância

```bash
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2 git
sudo usermod -aG docker $USER && newgrp docker
```

## 5. Swap — recomendado

A `t3.micro` tem 1 GB. O `docker build` (pip + dependências) pode encostar no
limite. 2 GB de swap evitam a falha, sem custo:

```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

## 6. Código e subida

```bash
git clone https://github.com/paulo9405/desafio-quick-filler.git
cd desafio-quick-filler

export QF_DOMINIO=seu.dominio.aqui
docker compose -f docker-compose.prod.yml up -d --build
```

O Caddy emite o certificado sozinho no primeiro acesso. Acompanhe:

```bash
docker compose -f docker-compose.prod.yml logs -f caddy
```

## 7. Validação

```bash
curl -i https://$QF_DOMINIO/healthz          # 200
curl -I  http://$QF_DOMINIO/                 # 308 -> https
curl -sI https://$QF_DOMINIO:8000/ || echo "8000 fechada (correto)"
```

## Manutenção

```bash
docker compose -f docker-compose.prod.yml logs -f app      # logs (sem PII)
docker compose -f docker-compose.prod.yml restart app      # reiniciar
docker compose -f docker-compose.prod.yml down             # parar
docker stats --no-stream                                    # memória
```

Os dados vivem em volumes Docker sobre o EBS: `qf-data` (banco + PDFs) e
`caddy-data` (certificados). Sobrevivem a `down`/`up` e a reinício da
instância. `down -v` apaga tudo.

## Custo

`t3.micro` está no free tier de 12 meses (750 h/mês) para contas elegíveis.
Fora disso, ~US$ 8–10/mês mais EBS. **Lembre de encerrar a instância quando o
processo seletivo terminar.**
