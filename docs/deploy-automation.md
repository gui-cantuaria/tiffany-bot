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
