# PhishGuard — Network Security

Machine-learning phishing URL detection for the PhishGuard browser extension.
A URL is turned into the 30 phishing-indicator features of the classic UCI
"Phishing Websites" dataset in real time (DNS, SSL, page HTML, URL heuristics),
then scored by a tiered RandomForest model and returned with a human-friendly
verdict (`low` / `medium` / `high` risk).

The backend is deployed **serverlessly** on AWS: **API Gateway (HTTP API) →
AWS Lambda (container image) → private S3 model registry**, with MongoDB only
for storing user feedback. No EC2, no always-on compute.

```
Browser extension
      │ HTTPS (POST /predict_url, /feedback)
      ▼
API Gateway HTTP API
      │
      ▼
AWS Lambda   (feature extraction + ML inference, model cached in memory)
      │  IAM: s3:GetObject
      ▼
S3 model registry  (immutable model versions + production manifest)
```

## Repository layout

```
aws/
  lambda/                    Lambda container image (app code, no model binaries)
    Dockerfile
    handler.py               Lambda entry point (routing, inference, feedback)
    requirements.txt
  scripts/
    package_model.py         package trained artifacts -> immutable S3 version
    publish_model.py         evaluate candidate vs production, promote on pass
    rollback_model.py        point production back to a previous version
  infrastructure/
    network-security-stack.yaml   CloudFormation: S3 + Lambda + API Gateway + IAM
networksecurity/
  serving/                   S3 model registry + cold-start bootstrap
  utils/feature_extraction/  real-time feature extractor + scorer
  database/                  MongoDB feedback repository
  constants/                 shared constants
  exception/, logging/       shared plumbing
extension/, extension-firefox/   Chrome/Edge and Firefox extension clients
collect_real_data.py         collect labeled real URLs + features (retraining)
train_models.py              train model_url.pkl / model_full.pkl + write metrics.json
train_models_real.py         train on real extracted features vs CSV models
train_from_feedback.py       fold user feedback into the training set
tests/                       offline test suite (S3 / runtime stubbed)
```

## Prerequisites

- An AWS account with permission to manage **CloudFormation, ECR, Lambda,
  API Gateway, S3, CloudWatch Logs and IAM**.
- **Docker** (only for the manual CLI path — the GitHub Actions path builds the
  image in CI).
- A **MongoDB Atlas** connection string (only `POST /feedback` uses it;
  inference works without it).
- The repo pushed to GitHub — the CI/CD workflows run from there.

## Local development

```bash
pip install -r requirements.txt

python train_models.py          # trains final_model/{model_url,model_full}.pkl
                                # and writes metrics.json (needed by package_model.py)
python -m pytest tests          # offline test suite (38 tests)
```

`python -m pytest tests -k "not scorer"` is what CI runs — `test_scorer.py`
loads the trained models from `final_model/` and is therefore only run locally
after training.

## Deployment (serverless, step by step)

> Detailed reference: [`aws/README.md`](aws/README.md).

### 1. Push to GitHub and configure secrets

Add the following **repository secrets** (Settings → Secrets → Actions):

| Secret | Required | Purpose |
| ------ | -------- | ------- |
| `AWS_ACCESS_KEY_ID` | yes | AWS credentials for ECR / CloudFormation |
| `AWS_SECRET_ACCESS_KEY` | yes | AWS credentials |
| `AWS_REGION` | yes | e.g. `us-east-1` |
| `MONGODB_URL` | yes* | Feedback database (skip to deploy without feedback) |
| `API_KEY` | optional | Shared secret checked against the `X-API-Key` header |

### 2. Run the `deploy-lambda` workflow

In the Actions tab, run **deploy-lambda** (`workflow_dispatch`, defaults are
fine). It:

1. runs the offline test suite (`ci` gate);
2. creates the ECR repository;
3. builds and pushes the inference image;
4. deploys the CloudFormation stack, which provisions the **S3 model
   registry bucket**, the **Lambda function** (image-based), its **IAM role**
   (least privilege: `s3:GetObject` on `models/*` and `production/*`), and the
   **HTTP API** with all routes.

The bucket must exist before the model can be packaged — the stack creates it.

### 3. Train and package an immutable model version

Run on a machine that has the trained artifacts (`final_model/`):

```bash
python train_models.py          # produces final_model/*.pkl and metrics.json

python aws/scripts/package_model.py \
  --bucket networksecurity-model-registry \
  --models-dir final_model \
  --metrics-json metrics.json \
  --trained-at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --trained-from Network_Data/phisingData.csv
```

This uploads `s3://networksecurity-model-registry/models/vN/` (artifacts +
`metadata.json` with SHA-256 hashes and metrics). Versions are **immutable** —
existing versions are never overwritten.

### 4. Promote the version to production

Run the **promote-model** workflow with `version` = the new `vN` (or use the
script directly):

```bash
python aws/scripts/publish_model.py --bucket networksecurity-model-registry --version v1
```

The promotion gate requires `accuracy >= 0.6` **and** the candidate must meet or
beat the current production score (pass `--force` to bypass). Promotion writes
`production/manifest.json`, which is the source of truth for the live model.

### 5. Verify the API

The deploy workflow prints the `ApiEndpoint`, e.g.
`https://<api-id>.execute-api.us-east-1.amazonaws.com`.

```bash
curl https://<api-id>.execute-api.<region>.amazonaws.com/health

curl -X POST https://<api-id>.execute-api.<region>.amazonaws.com/predict_url \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"url": "https://google.com"}'

curl https://<api-id>.execute-api.<region>.amazonaws.com/api/v1/model/version
```

### 6. Point the browser extension at the API

Open `extension/options.html` → set **Backend URL** to the `ApiEndpoint` and
**API key** if the stack was deployed with one. See `extension/README.md`.

## Manual CLI deployment (no GitHub Actions)

1. `aws ecr create-repository --repository-name phishguard-inference-dev`
2. Build and push the image from `aws/lambda/Dockerfile`.
3. `aws cloudformation deploy --template-file aws/infrastructure/network-security-stack.yaml --stack-name network-security-inference-dev --capabilities CAPABILITY_NAMED_IAM --parameter-overrides Environment=dev BucketName=networksecurity-model-registry LambdaImageUri=<ecr-image-uri> ModelVersion=v1 MongodbUrl="$MONGODB_URL" ApiKey="$API_KEY"`
4. Package + promote the model (steps 3–4 above).

## Model lifecycle (retraining and updates)

```text
retrain → package_model.py (new immutable vN) → publish_model.py / promote-model
   → deploy-lambda (redeploy, or leave model_version empty so Lambda follows
     the production manifest on its next cold start)
```

- **Rollback**: `python aws/scripts/rollback_model.py --bucket networksecurity-model-registry --version vN` flips the manifest back (artifacts are immutable) — then redeploy.
- **Data collection for retraining**: `collect_real_data.py` (OpenPhish feed + benign list), `train_from_feedback.py` (folds user "wrong" ratings from MongoDB into the training set), then `train_models_real.py`.
- The Lambda loads the model **once per execution environment** (cold start); warm invocations never touch S3.

## API reference

| Method | Path | Description |
| ------ | ---- | ----------- |
| POST | `/predict_url` | Score one URL (the extension uses this) |
| POST | `/predict_urls` | Score a batch (1–100 URLs) |
| POST | `/api/v1/analyze` | Alias of `/predict_url` |
| POST | `/feedback` | Record user feedback (best-effort) |
| POST | `/api/v1/feedback` | Alias of `/feedback` |
| GET | `/api/v1/model/version` | Live model version + metrics |
| GET | `/health` | Liveness |

Optional auth: when the stack is deployed with `ApiKey` /
`PHISHGUARD_API_KEY`, requests need an `X-API-Key` header.

## CI/CD workflows

| Workflow | Trigger | Purpose |
| -------- | ------- | ------- |
| `ci.yml` | push to `main` / PR | Runs the offline test suite |
| `deploy-lambda.yml` | manual (`workflow_dispatch`) | Tests → build ECR image → deploy/update the serverless stack |
| `promote-model.yml` | manual | Evaluate + promote a candidate model version |

Secrets are passed at deploy time via GitHub secrets; no AWS keys or MongoDB
credentials are stored in the repository (`.env` is gitignored).

## Operational notes

- **Costs**: Lambda + HTTP API + S3 + CloudWatch only — no always-on compute.
- **Cold starts**: the image bundles scikit-learn/tldextract/bs4 (~1 GB); the
  first request per execution environment is slow. Stack defaults: 1024 MB
  memory, 30 s timeout.
- **Auth**: optional shared API key checked against the `X-API-Key` header.
  There is no rate limiting on the Lambda path — add an API Gateway usage plan
  or a WAF rule if you need request throttling.
- **Feedback**: written to MongoDB; failures are dropped best-effort so they
  never fail a request.
- **Logging**: structured JSON to CloudWatch (request ID, model version,
  duration, cold-start flag).
