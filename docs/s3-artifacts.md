# Datasets and Models on S3

The training datasets and every model version in the registry can be
stored in Amazon S3, so a new machine or a scheduled retraining job can
start from the same files without rebuilding them. The same code talks
to MinIO locally, since MinIO speaks the S3 API.

```text
data/processed/historical_dataset_*.csv  ->  s3://<bucket>/ml/datasets/
ml/artifacts/model_registry/versions/<v>  ->  s3://<bucket>/ml/models/<v>/
ml/artifacts/model_registry/registry.json ->  s3://<bucket>/ml/registry/registry.json
```

The code is in `ml/src/.../storage/` (`s3.py` for the client,
`artifacts.py` for the layout above) and the command line is
`scripts/storage/s3_artifacts.py`.

## Configuration

| Variable | Purpose |
|---|---|
| `ARTIFACT_BUCKET` | Bucket name. S3 is off when this is empty. |
| `AWS_REGION` | Bucket region, default `us-west-2` |
| `S3_ENDPOINT_URL` | Set only for MinIO, e.g. `http://localhost:9000` |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | Credentials, or any other source boto3 reads (profile, SSO, pod identity) |

Values in `.env` are loaded automatically. For the local MinIO from
`infra/docker`:

```bash
ARTIFACT_BUCKET=ai-earth-artifacts
S3_ENDPOINT_URL=http://localhost:9000
AWS_ACCESS_KEY_ID=ai_earth
AWS_SECRET_ACCESS_KEY=ai_earth_dev
AWS_REGION=us-east-1
```

## Commands

```bash
S3="uv run --project ml python scripts/storage/s3_artifacts.py"
$S3 check                         # bucket reachable and credentials valid
$S3 push-datasets                 # upload the historical datasets and manifests
$S3 pull-datasets                 # download them into data/processed/
$S3 push-model                    # upload the current registry version and registry.json
$S3 push-model --version v1       # upload a specific version
$S3 pull-model --serve            # download the remote current version and serve it
$S3 list --prefix ml/models/
$S3 upload <file> <key>           # any single file
$S3 download <key> <file>
```

`pull-model` without `--version` reads the remote `registry.json` to find
the version in service. `--serve` deploys it to
`ml/artifacts/production_model_v1` with the same atomic swap retraining
uses.

## Integrity and errors

- Every upload stores the file's SHA-256 in the object metadata, then
  reads the object back and checks its size and checksum.
- Every download is written to a temporary file first and checked
  against the stored checksum. A mismatch deletes the temporary file and
  leaves any existing local copy untouched.
- Object keys are checked before use: no empty, `.` or `..` segments, no
  leading `/`, at most 1024 bytes.
- A model version is uploaded before `registry.json`, so the remote
  registry never points at a version that is not there yet.
- Requests retry up to 3 times, with a 3 s connect timeout and a 60 s
  read timeout.
- Failures are reported in plain terms (bucket does not exist, object
  not found, access denied, no credentials, endpoint unreachable), and
  the command exits with code 1. A missing `ARTIFACT_BUCKET` exits with
  code 2.

## In the retraining pipeline

When `ARTIFACT_BUCKET` is set, `scripts/models/auto_retrain.py` uploads
each new candidate, the updated `registry.json` and the run log after
every run, so every model the gate has scored is kept in S3, promoted or
not.

## On AWS

`infra/terraform/modules/storage` creates the bucket
(`<project>-artifacts-<account id>`) with public access blocked, AES-256
encryption, and versioning, so an overwritten dataset or registry can be
recovered. Old versions expire after 90 days (`noncurrent_version_days`),
and unfinished multipart uploads are removed after 7. The backend's pod
identity already has read, write and list access to the bucket.

## Tests

`ml/tests/storage/` runs against an in-memory S3 from `moto`, so it
needs no account or network. The commands above were also run against
the local MinIO, including a 211 MB dataset round trip with matching
checksums, a tampered object being rejected, and the missing-bucket,
wrong-password and unreachable-endpoint errors.
