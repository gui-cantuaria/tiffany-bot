# Fluxo automático: pedir no Cursor → deploy na VPS

Você **não precisa** entrar na VPS para cada mudança de código. O fluxo ideal:

```
Você pede no Cursor  →  Agent edita o código  →  commit + push  →  GitHub Actions  →  VPS atualizada
```

## O que você faz

1. Descreva o que quer em português (ex.: *"corrige o t!p com playlist do Spotify"*, *"sobe o limite da fila pra 80"*).
2. Quando estiver pronto, diga: **"commita e faz deploy"** (ou só *"pode commitar"*).
3. O agent aplica as mudanças, faz push pro `main` e o GitHub Actions roda o deploy sozinho.

## O que acontece na VPS (automático)

O workflow `.github/workflows/deploy.yml` faz SSH na VPS e executa `scripts/deploy.sh`, que:

- dá `git fetch` + checkout dos arquivos atualizados
- instala deps no `.venv` (Python 3.11)
- reinicia o `tiffany-bot.service`
- mantém o timer do WARP healthcheck

**Modo:** systemd (não Docker). Não precisa rodar comandos manuais na VPS.

## Setup único (só falta fazer 1 vez)

Se o deploy automático ainda não estiver configurado:

### Na VPS

```bash
bash /opt/tiffany-bot/scripts/setup-github-actions.sh
```

O script mostra o **IP** e a **chave privada** para colar no GitHub.

### No GitHub

Repositório → **Settings → Secrets and variables → Actions**:

| Secret | Valor |
|--------|--------|
| `VPS_HOST` | IP da VPS (ex.: `187.77.48.146`) |
| `VPS_SSH_KEY` | chave privada inteira (`-----BEGIN...`) |

### Testar

- **Actions** → **Deploy to VPS** → **Run workflow**, ou
- qualquer push no `main` que altere `.py`, `scripts/**`, `requirements.txt`

## Quando ainda precisa entrar na VPS

Só para coisas **fora do código**:

- editar `.env` (tokens, IDs de canal)
- instalar WARP pela primeira vez (`bash scripts/warp-setup.sh`)
- ver logs: `journalctl -u tiffany-bot -n 50 --no-pager`

## Ver se o deploy passou

GitHub → **Actions** → último run de **Deploy to VPS** (verde = ok).

Na VPS (opcional):

```bash
systemctl status tiffany-bot
```

## Runtime JSON state

O bot **não usa banco de dados** — histórico, filas e memória ficam em arquivos JSON na raiz do projeto (`/opt/tiffany-bot/`). O deploy automático **não sobrescreve** esses arquivos (só faz checkout de `.py`, scripts e deps).

| Arquivo | Conteúdo |
|---------|----------|
| `notices_history.json` | Dedup de notícias (SimHash, títulos) |
| `notices_queue.json` | Fila de posts pendentes |
| `chat_memory.json` | Memória de conversa `t!c` (TTL 24h) |
| `voice_state.json` | Fila/música atual por servidor |
| `voice_stats.json` | Contadores de uso |
| `game_history.json` | Última recomendação `t!g` por usuário |

**Backup / migração de VPS:** copie `.env` + `*.json` antes de trocar de máquina:

```powershell
# Do PC (PowerShell) — ajuste o IP
scp root@187.77.48.146:/opt/tiffany-bot/.env .
scp root@187.77.48.146:/opt/tiffany-bot/*.json .
```

Na VPS nova, envie de volta para `/opt/tiffany-bot/`. Sem isso, dedup de notícias, memória de chat e histórico de jogos recomeçam do zero.

O backup semanal da Hostinger cobre o disco inteiro, mas **restaurar snapshot** é mais pesado que um `scp` dos JSONs — vale guardar cópia local ocasional se o histórico for importante.
