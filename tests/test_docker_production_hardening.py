"""
Tiffany OS — Automated Docker Production Hardening Test Suite
============================================================
Validates production Docker configuration and failure recovery controls:
1. Dockerfile application healthchecks (infra.health), non-root execution (tiffanyuser:10001).
2. docker-compose.yml service definitions (PostgreSQL, Redis, Lavalink, Tiffany Bot).
3. Condition-based service dependencies (depends_on condition: service_healthy).
4. Application & Infrastructure healthchecks (pg_isready, redis-cli ping, nc, python -m infra.health).
5. Resource limits (CPUs, RAM caps) preventing host exhaustion.
6. Log rotation policies (json-file 10m max-size).
7. Production host daemon enablement and crontab automation scripts.
8. Disaster recovery backup integrity verification (gzip -t) and restore validation.
"""

import unittest
import os

class TestDockerProductionHardening(unittest.TestCase):
    def setUp(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.dockerfile_path = os.path.join(self.base_dir, "Dockerfile")
        self.compose_path = os.path.join(self.base_dir, "docker-compose.yml")
        self.setup_script = os.path.join(self.base_dir, "scripts", "setup-production-host.sh")
        self.backup_script = os.path.join(self.base_dir, "scripts", "backup-db.sh")
        self.restore_script = os.path.join(self.base_dir, "scripts", "restore-db.sh")
        self.health_probe = os.path.join(self.base_dir, "infra", "health.py")

    def test_dockerfile_non_root_and_application_healthcheck(self):
        """Verify Dockerfile uses application health probe infra.health and non-root execution."""
        self.assertTrue(os.path.exists(self.dockerfile_path), "Dockerfile missing")
        with open(self.dockerfile_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("USER tiffanyuser", content, "Dockerfile must specify USER tiffanyuser")
        self.assertIn("HEALTHCHECK", content, "Dockerfile must define HEALTHCHECK directive")
        self.assertIn("python -m infra.health", content, "Dockerfile must execute application health probe")
        self.assertIn("10001", content, "Dockerfile must specify UID/GID 10001")

    def test_docker_compose_production_services(self):
        """Verify docker-compose.yml contains all required production services and volumes."""
        self.assertTrue(os.path.exists(self.compose_path), "docker-compose.yml missing")
        with open(self.compose_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("postgres:", content, "postgres service missing in compose")
        self.assertIn("redis:", content, "redis service missing in compose")
        self.assertIn("lavalink-primary:", content, "lavalink-primary service missing in compose")
        self.assertIn("tiffany-bot:", content, "tiffany-bot service missing in compose")

        self.assertIn("postgres-data:", content, "postgres-data volume missing")
        self.assertIn("redis-data:", content, "redis-data volume missing")

    def test_docker_compose_healthchecks_and_dependencies(self):
        """Verify application healthchecks and condition: service_healthy on dependencies."""
        with open(self.compose_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Healthchecks
        self.assertIn("healthcheck:", content, "healthcheck directives missing")
        self.assertIn("pg_isready", content, "postgres pg_isready healthcheck missing")
        self.assertIn("redis-cli", content, "redis redis-cli healthcheck missing")
        self.assertIn("python3 -m infra.health", content, "bot application probe healthcheck missing")
        self.assertIn("condition: service_healthy", content, "condition: service_healthy missing")

    def test_docker_compose_resource_limits_and_logging(self):
        """Verify resource limits and log rotation limits across services."""
        with open(self.compose_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Log rotation
        self.assertIn('driver: "json-file"', content, "json-file logging driver missing")
        self.assertIn('max-size: "10m"', content, "max-size 10m log limit missing")

        # Resource limits
        self.assertIn("cpus:", content, "cpu limits missing")
        self.assertIn("memory:", content, "memory limits missing")

    def test_setup_host_and_dr_scripts(self):
        """Verify setup-production-host.sh, backup-db.sh (with gzip -t), and restore-db.sh exist."""
        self.assertTrue(os.path.exists(self.setup_script), "scripts/setup-production-host.sh missing")
        self.assertTrue(os.path.exists(self.backup_script), "scripts/backup-db.sh missing")
        self.assertTrue(os.path.exists(self.restore_script), "scripts/restore-db.sh missing")
        self.assertTrue(os.path.exists(self.health_probe), "infra/health.py probe missing")

        with open(self.backup_script, "r", encoding="utf-8") as f:
            backup_src = f.read()
        self.assertIn("gzip -t", backup_src, "backup-db.sh must perform gzip compression integrity check")

        with open(self.restore_script, "r", encoding="utf-8") as f:
            restore_src = f.read()
        self.assertIn("pg_tables", restore_src, "restore-db.sh must validate public table count after restore")

if __name__ == "__main__":
    unittest.main()
