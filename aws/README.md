# PhishGuard AWS Serverless Deployment

Serverless model-serving infrastructure for the PhishGuard browser-extension
backend. Inference runs on **AWS Lambda** behind an **API Gateway HTTP API**;
model artifacts live in a **private S3 registry** with immutable versions and
an explicit production manifest. No EC2, no Redis, no always-on compute.

```
Browser Extension
        |
        | HTTPS
        v
API Gateway HTTP API
        |
        v
AWS Lambda  (preprocessor + ML inference)
        |
        | IAM (s3:GetObject)
        v
S3 model registry (immutable versions + production manifest)
```

## Repository layout

```
aws/
  lambda/
    Dockerfile            Lambda container image (app code, no model binaries)
    handler.py            Lambda entry point (routes, inference, feedback)
    requirements.txt      minimal ML/runtime deps for the image
  scripts/
    package_model.py      package trained artifacts -> immutable S3 version
    publish_model.py      evaluate candidate vs production, promote on pass
    rollback_model.py     point production back to a previous version
  infrastructure/
    network-security-stack.yaml   CloudFormation IaC
networksecurity/
  serving/
    model_store.py        manifest reader + artifact download/SHA-256 verify
    runtime.py            cold-start bootstrap (model loaded once per env)
  utils/feature_extraction/
    scorer.py             scoring logic (models dir now from PHISHGUARD_MODEL_DIR)
.github/workflows/
  deploy-lambda.yml       build image + deploy/update the serverless stack
  promote-model.yml       evaluate + promote a candidate model in CI
```

## S3 model registry

```
s3://<bucket>/
  models/
    v1/  model_url.pkl  model_full.pkl  preprocessor.pkl  metadata.json
    v2/  ...
    vN/  ...
  production/
    manifest.json              <- source of truth for the live model
    manifest-history/
      v1.json ... vN.json      <- promotion records (used for rollback)
  staging/                     <- optional prefix for unpublished candidates
```

`metadata.json` records SHA-256 hashes and training metrics per version;
`production/manifest.json` points at the approved version:

```json
{
  "version": "v12",
  "model": "models/v12/model_url.pkl",
  "model_full": "models/v12/model_full.pkl",
  "preprocessor": "models/v12/preprocessor.pkl",
  "accuracy": 0.94,
  "precision": 0.93,
  "recall": 0.95,
  "f1": 0.94,
  "promoted_at": "2026-08-12T00:00:00Z"
}
```

## Endpoints

| Method | Path                 | Description                                  |
| ------ | -------------------- | -------------------------------------------- |
| POST   | `/predict_url`       | score one URL (extension uses this)          |
| POST   | `/predict_urls`      | score a batch (1-100 URLs)                   |
| POST   | `/api/v1/analyze`    | alias of `/predict_url`                      |
| POST   | `/feedback`          | record user feedback (best-effort)           |
| POST   | `/api/v1/feedback`   | alias of `/feedback`                         |
| GET    | `/api/v1/model/version` | live model version + metrics              |
| GET    | `/health`            | liveness                                     |

Optional auth: set `ApiKey` (stack parameter) / `PHISHGUARD_API_KEY`; requests
then need an `X-API-Key` header.

## Quick start

### 1. Build and push the inference image

```bash
aws ecr create-repository --repository-name phishguard-inference-dev 2>/dev/null || true
docker build -f aws/lambda/Dockerfile -t phishguard-inference-dev:latest .
docker tag phishguard-inference-dev:latest \
  <account>.dkr.ecr.<region>.amazonaws.com/phishguard-inference-dev:latest
aws ecr get-login-password | docker login --username AWS --password-stdin \
  <account>.dkr.ecr.<region>.amazonaws.com
docker push <account>.dkr.ecr.<region>.amazonaws.com/phishguard-inference-dev:latest
```

### 2. Create the stack

```bash
aws cloudformation deploy \
  --template-file aws/infrastructure/network-security-stack.yaml \
  --stack-name network-security-inference-dev \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    Environment=dev \
    BucketName=networksecurity-model-registry \
    LambdaImageUri=<account>.dkr.ecr.<region>.amazonaws.com/phishguard-inference-dev:latest \
    ModelVersion=v1 \
    MongodbUrl="$MONGODB_URL" \
    ApiKey="$API_KEY"
```

Creates the private bucket, the Lambda role (least privilege: `s3:GetObject`
on `models/*` and `production/*`), the inference Lambda, the HTTP API with
routes, and the CloudWatch log group. Re-run the same command to update.

### 3. Train, then package an immutable version

Run on the training machine (has the artifacts):

```bash
python train_models.py            # or train_models_real.py / train_from_feedback.py
python aws/scripts/package_model.py \
  --bucket networksecurity-model-registry \
  --models-dir final_model \
  --metrics-json metrics.json \
  --trained-at 2026-08-12T00:00:00Z \
  --trained-from Network_Data/phisingData.csv
```

Creates `s3://<bucket>/models/vN/...` with hashes. Never overwrites an
existing version.

### 4. Evaluate and promote

```bash
python aws/scripts/publish_model.py \
  --bucket networksecurity-model-registry --version v13
```

Fails (non-zero) unless the candidate passes the gate
(`accuracy >= 0.6` and `>= production accuracy`). Pass `--force` to bypass.
Equivalent CI job: the **promote-model** workflow.

### 5. Deploy the new model version to Lambda

Re-run step 2 with `ModelVersion=v13` (new Lambda execution environments cold
start into v13; warm ones serve the previous version until recycled), or use
the **deploy-lambda** workflow (Actions tab) which builds + pushes the image
and updates the stack in one run.

Point the extension's **Options -> Backend URL** at the `ApiEndpoint` output.

### 6. Rollback

```bash
python aws/scripts/rollback_model.py --bucket networksecurity-model-registry --version v12
```

Flips the production manifest back to v12 (artifacts are immutable, no
retraining), then redeploy the stack with `ModelVersion=v12`.

## How the Lambda serves models

- Cold start: read the pinned version (`PHISHGUARD_MODEL_VERSION`) or the
  production manifest, download the artifacts to `/tmp`, verify SHA-256, load
  the scorer once. Kept in memory for the environment's lifetime.
- Warm invocation: no S3, no downloads - inference only.
- The model is never fetched on the per-request path.

## Model updates and Lambda environments

New deployments create new execution environments that load the new version on
their cold start. Existing warm environments may serve the previous version
until they are recycled - eventual replacement by design. If strict version
consistency is ever required, publish a Lambda version/alias and point the API
integration at it:

```bash
aws lambda publish-version --function-name network-security-inference-dev
aws lambda update-alias --function-name network-security-inference-dev --name prod --function-version <N>
aws apigatewayv2 update-integration --api-id <api-id> --integration-id <id> \
  --integration-uri "arn:aws:apigateway:<region>:lambda:path/2015-03-31/functions/arn:aws:lambda:<region>:<account>:function:network-security-inference-dev:prod/invocations"
```

## Operational notes

- **Logging**: structured JSON to CloudWatch (request ID, model version,
  duration, result, cold-start flag). URLs are logged by host only.
- **Feedback**: MongoDB via `MONGODB_URL`; failures are dropped best-effort
  (never fails the request), matching the extension's silent-drop contract.
- **Costs**: Lambda + HTTP API + S3 + CloudWatch only. Fits well under the
  <500 users/day target.
- **Secrets**: never store AWS keys in code/repo. Use IAM roles. Keep
  `MONGODB_URL`/`API_KEY` in GitHub secrets (or SSM) and pass them at deploy.
- **Local testing**: no AWS account needed - `tests/test_model_store.py`
  exercises the registry with a stubbed S3 client and
  `tests/test_lambda_handler.py` exercises the handler with a stubbed runtime.
