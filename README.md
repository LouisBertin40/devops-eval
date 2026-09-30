# devops-eval

[![CI](https://github.com/LouisBertin40/devops-eval/actions/workflows/ci.yml/badge.svg)](https://github.com/LouisBertin40/devops-eval/actions/workflows/ci.yml)
[![CD](https://github.com/LouisBertin40/devops-eval/actions/workflows/cd.yml/badge.svg)](https://github.com/LouisBertin40/devops-eval/actions/workflows/cd.yml)

API Flask minimale avec Redis : `/health` (vérifie Redis, 503 s'il ne répond pas),
`/visits` (compteur stocké dans Redis), `/metrics` (métriques Prometheus).

## Lancer le projet en local

Prérequis : Docker Desktop, Python 3.12+.

```bash
docker compose up -d --build
```

| Service     | URL                                                              |
| -------------| ------------------------------------------------------------------|
| Application | http://localhost:5000/health                                     |
| Métriques   | http://localhost:5000/metrics                                    |
| Prometheus  | http://localhost:9090 (cibles : `/targets`, alertes : `/alerts`) |

Lancer les tests et les lints (Redis doit tourner) :

```bash
docker run -d --name redis-dev -p 6379:6379 redis:7-alpine
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt   # Linux/macOS : .venv/bin/pip
.venv/Scripts/python -m pytest -v
.venv/Scripts/flake8 .
.venv/Scripts/yamllint .
```

## Docker

- Build multi-stage sur `python:3.12-slim` : Le premier stage sert à installer les dépendences et le second ne récupère que le venv, cela donne une image finale plus légère qui contient moins de choses. Cela limite aussi la surface d'attaque.
- Taille de l'image : 208 Mo sur disque, 50 Mo compressés.
- Utilisateur non-root `appuser` : Pour des raisons de sécurité, si l'app est piratée, le pirate pourait obtenir les droits admin,c'est pour cela que l'on applique toujours le principe du moindre privilège en bloquant l'accès root et en utilsant appuser.
- `HEALTHCHECK` qui appelle `/health` (en Python, `curl` n'étant pas dans l'image slim).
- Servie par gunicorn (serveur de production), pas le serveur de dev de Flask.
- `docker-compose.yml` : `web` + `redis` (+ `prometheus`), `web` attend que Redis soit
  healthy (`depends_on: condition: service_healthy`), données Redis dans un volume nommé.

## CI — `.github/workflows/ci.yml`

Déclenchée sur chaque pull request et chaque push sur `main`. Permissions : `contents: read`.

`lint` (flake8 + yamllint) → `test` (matrice Python 3.12 / 3.13, service Redis réel) →
`build` (build de l'image, récupération des rapports) → `ci-ok`.

- Action locale `.github/actions/setup-python-deps` (setup Python + cache pip + install),
  appelée par les jobs au lieu de dupliquer ces étapes.
- Cache pip : cache HIT au second run ([preuve](docs/cache-hit.png)).
- Rapports JUnit et couverture publiés en artefacts, même en cas d'échec (`if: always()`),
  puis récupérés par le job `build` (`download-artifact`).
- `timeout-minutes` sur chaque job.
- `main` est protégée : merge uniquement par PR, avec le check `ci-ok` obligatoire.
  Le if: always() est nécessaire, car sans cela un job sauté serait considéré comme validé par Github et donc la vérification passerait, or, ce n'est pas ce que l'on veut. la condition always() va forcer ci-ok à s'exécuter même si un job précédent a échoué. Il regarde alors le résultat des autres jobs et s'il y en a un qui est échoué, il échouera aussi.

## CD — `.github/workflows/cd.yml`

Déclenché après une CI verte sur `main` (`workflow_run`), ou à la main
(`workflow_dispatch`, input `environment: production`).

1. `build-and-push` : construit l'image et la pousse sur
   `ghcr.io/louisbertin40/devops-eval` avec 3 tags : `latest`, SHA court, `1.0.<run>`.
   Seul ce job a `packages: write`.
2. `deploy` : tourne sur un **runner self-hosted** (ma machine), stack `devops-eval-prod`
   sur le port 8080. Vérification `curl` de `/health` avec 3 retries ; en cas d'échec,
   rollback vers le SHA précédent et job en échec ([preuve](docs/rollback.png)).

Sécurité du runner self-hosted (repo public) : N'importe qui pourrait ouvrir une PR avec du code malveillant et le faire exécuter sur l'appareil qui héberge le runner. Pour éviter cela, seul le job deploy utilise le runner et il ne se lance que sur main ou à la main. La CI des pull requests tourne sur les runners de GitHub, donc le code d'une PR ne s'exécute jamais sur la machine qui héberge le runner.

Authentification au registry par `GITHUB_TOKEN` uniquement, aucun secret affiché.

## Métriques et alertes

`/metrics` expose :
- `http_requests_total{endpoint, code}` : compteur de requêtes ;
- `http_request_duration_seconds{endpoint}` : histogramme de latence (p95/p99) ;
- `app_version_info{version}` : SHA du commit déployé (injecté au build).

Alertes (`monitoring/alerts.yml`) :

| Alerte                | Condition                   | `for` | Justification                                                                                                                                    |
| -----------------------| -----------------------------| -------| --------------------------------------------------------------------------------------------------------------------------------------------------|
| `TauxErreurs5xxEleve` | 5xx / total > 5 % sur 1 min | 2 min | Les 5% permettent de tolérer une erreur isolée mais en cas de vraie panne qui impacterait l'ensemble des utilisateurs, cela remonterait l'alerte. Le délais de 2 minutes empêche de remonter des alertes pour une courte indisponibilité comme un redémarrage. |
| `LatenceP95Degradee`  | p95 > 500 ms sur 5 min      | 5 min | Montre les requêtes lentes que la moyenne cache. L'app répond normalement en quelques ms, donc 500 ms est une vraie dégradation.                 |

Test : Redis coupé → les deux alertes passent en Firing ([preuve](docs/alertes-firing.png)).
