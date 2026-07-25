# High Availability — Tiffany Bot (99.999% target)

**Reality check:** 99.999% = ≤5.26 minutes downtime/year. A single VPS + PM2/systemd **cannot** meet this. Discord also limits one Gateway per bot token until you **shard**.

## Phase map

| Phase | Guilds | Uptime target | Stack |
|-------|--------|---------------|-------|
| **0 (today)** | <2k | 99.9% | Hostinger VPS, systemd, `launcher.py`, optional Lavalink Docker |
| **1** | 2k–10k | 99.95% | PostgreSQL + Redis, Lavalink 2 nodes, health webhooks |
| **2** | 10k–100k | 99.99% | K8s multi-AZ, AutoShardedClient, worker split (news/offers) |
| **3** | 100k+ | 99.999% | Multi-region Lavalink, DB replicas, active-active shards |

## Architecture (Phase 2+)

```
                    ┌─────────────────┐
                    │  Discord Gateway │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
        Bot Shard 0    Bot Shard 1    Bot Shard N
              │              │              │
              └──────────────┼──────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
   Redis Cluster      PostgreSQL            Lavalink Pool
   (cache, RL,        (giveaways,           (node A, B, C
    premium, i18n)     premium, embeds)      + WARP each)
         │                   │
         └─────────┬─────────┘
                   ▼
            Worker pods (news RSS, offers scrape)
```

## Sharding (mandatory >2,500 guilds)

```python
# notices.py — future
intents = discord.Intents.default()
# ...
discord_client = commands.AutoShardedBot(
    shard_count=4,  # or automatic via gateway bot session
    ...
)
```

- **One token**, N shard processes OR one process with AutoShardedBot
- Lavalink/wavelink: all shards share same `wavelink.Pool` nodes
- Redis/PostgreSQL: shared state across shards

## Lavalink redundancy

- **2+ nodes** in different AZs; bot connects to all via `LAVALINK_NODES`
- **WARP/proxy on each node** (`JAVA_TOOL_OPTIONS` SOCKS5) — not on bot
- Health: Prometheus + alert if node disconnects; wavelink failover automatic

## Database

- **PostgreSQL** primary + read replica (premium reads, stats)
- Migrations: `schema/001_initial.sql` applied on startup
- Backups: daily snapshot + WAL; JSON files deprecated for giveaways/embeds

## Deploy

- **Kubernetes**: Deployment per shard, `PodDisruptionBudget`, rolling updates
- **Never** `pkill -9 python` — use graceful SIGTERM (already in launcher)
- GitHub Actions → rolling deploy per shard sequentially

## Monitoring

- Discord webhook health (launcher already supports)
- Uptime: Better Stack / Grafana Cloud
- SLO: Gateway latency, Lavalink node status, Redis/PG connectivity

## What we implemented in repo (foundation)

| Component | Path |
|-----------|------|
| Lavalink multi-node | `infra/audio/lavalink_nodes.py`, `LAVALINK_NODES` env |
| Redis optional | `infra/redis_client.py` |
| PostgreSQL optional | `infra/postgres.py`, `schema/001_initial.sql` |
| Premium cache | `infra/premium.py` |
| i18n JSON | `locales/`, `infra/i18n_loader.py` |

Next steps: enable `DATABASE_URL` + `REDIS_URL` on VPS, add second Lavalink service in `docker-compose.yml`, plan shard count before 2.5k guilds.
