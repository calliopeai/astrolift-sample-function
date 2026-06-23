# astrolift-sample-function

Fixture **R5** of the Astrolift topology catalog (spec
[42 — Sample Fixtures](../../astrolift-spec/specs/42-sample-fixtures.md)). It is
the **serverless / function** row of the execution gamut: a minimal, real Python
HTTP function that deploys as a **Knative Serving** Service and **scales to
zero** when idle.

## Topology

| Property | Value |
|---|---|
| Workload kind | `function` (Knative Serving) |
| Rendered object | `serving.knative.dev/v1` Service (no Deployment, no HPA) |
| Autoscaling | Knative-owned; `min_scale = 0` → scale-to-zero |
| Image | `docker.io/calliopeai/astrolift-sample-function:main-<sha7>` |
| Language | Python 3.12 + Flask, served by gunicorn |

A function differs from `sample-web`/`sample-api` (which render Deployments +
HPAs): Knative's autoscaler owns the replica count and drives it to **zero** with
no traffic, then **cold-starts** a pod on the next request. This fixture is built
for that lifecycle — a slim image, two pinned deps, and a cheap deterministic
compute job — so a cold start is fast and a single request produces a verifiable
result.

## Routes (the spec-42 §3.1 debug contract)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/compute?n=<int>` | Computed JSON: sum of squares of `1..n`, primality of `n` |
| `POST` | `/` | Same compute; `n` from a JSON or form body |
| `GET` | `/health` | `200` readiness/liveness probe (`healthcheck.kind="http"`, `value="/health"`) |
| `GET` | `/debug` | Diagnostic JSON (`app`, `version`, `kind="function"`, `hostname`, `uptime_s`, `env_seen`, `build`) |

`n` is clamped to `[0, 100000]` so a hostile value can't turn a scale-to-zero
function into a CPU sink. This fixture attaches no managed services, so `/debug`
reports `bindings: {}` and there is no `/selftest` (that surface belongs to
`sample-api`).

A structured startup banner is logged on every cold start:

```
startup app=sample-function kind=function version=<sha> hostname=<pod> listen_port=8080 bindings=none
```

### Example

```bash
curl "$URL/compute?n=12"
# {"n":12,"sum_of_squares":650,"sum_1_to_n":78,"is_prime":false,"computed_at":"..."}

curl -X POST "$URL/" -H 'content-type: application/json' -d '{"n":13}'
# {"n":13,"sum_of_squares":819,"sum_1_to_n":91,"is_prime":true,"computed_at":"..."}
```

## Manifest variant → matrix cell

| Variant | Cell (spec-42 §6) | Notes |
|---|---|---|
| `manifests/function.toml` | function (Knative) | `min_scale=0`, `max_scale=5`, `concurrency=10`, `timeout_seconds=60`, primary container port 8080, `http /health` healthcheck |

### Field mapping (TOML → Knative)

The §4 FUNCTION skeleton keys are authored verbatim; the backend parser maps
them to Knative as:

| `function.toml` key | Knative field |
|---|---|
| `concurrency` | `spec.template.spec.containerConcurrency` |
| `timeout_seconds` | `spec.template.spec.timeoutSeconds` |
| `min_scale` / `max_scale` | `autoscaling.knative.dev/{minScale,maxScale}` annotations |

## Build

GitHub Actions (`.github/workflows/build.yml`) builds on push to `main` and
pushes `docker.io/calliopeai/astrolift-sample-function` tagged `main-<sha7>`
(deterministic, used for deploy) and `latest`, authenticating with the org-level
`DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN` secrets. Build args (`GIT_SHA`,
`IMAGE_REF`, `BUILT_AT`) are threaded into the image and surfaced through
`/debug`.

## Run locally

```bash
pip install -r requirements.txt
python -m app.main        # http://localhost:8080

# or the production server (what the container runs):
gunicorn --bind 0.0.0.0:8080 app.main:app
```
