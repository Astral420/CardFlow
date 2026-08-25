# Testing the backend locally with real data (no frontend)

This walks through exercising the full pipeline — upload → crop → rotate →
hash → duplicate review → card log — against a real zip of card scans,
using only `curl` (or Postman/httpie if you prefer) and a local Postgres +
Redis + object storage stack. No frontend required; Phase 2 hasn't been
built yet.

Run all commands from the `card-tool-v1/` project root unless noted.

## 1. Choose your object storage for local testing

The pipeline uploads/downloads images from R2 (S3-compatible). For local
testing you have two options:

**Option A — real Cloudflare R2 (closest to production)**
Fill in `backend/.env` with your real R2 credentials:
```
R2_ACCOUNT_ID=...
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_BUCKET_NAME=card-tool
```

**Option B — local MinIO (no cloud account needed)**
Run a throwaway S3-compatible server in Docker:
```bash
docker run -d --name card-tool-minio -p 9000:9000 -p 9001:9001 \
  -e MINIO_ROOT_USER=minioadmin -e MINIO_ROOT_PASSWORD=minioadmin \
  minio/minio server /data --console-address ":9001"
```
Then set in `backend/.env`:
```
R2_ENDPOINT_URL=http://localhost:9000
R2_ACCESS_KEY_ID=minioadmin
R2_SECRET_ACCESS_KEY=minioadmin
R2_BUCKET_NAME=card-tool
```
Create the bucket once (MinIO doesn't auto-create it):
```bash
backend/.venv/Scripts/python -c "
import boto3
s3 = boto3.client('s3', endpoint_url='http://localhost:9000', aws_access_key_id='minioadmin', aws_secret_access_key='minioadmin')
s3.create_bucket(Bucket='card-tool')
print('bucket ready')
"
```
You can browse uploaded images at http://localhost:9001 (login
`minioadmin` / `minioadmin`) — handy for eyeballing crop quality.

## 2. Start Postgres + Redis

```bash
docker compose up -d postgres redis
```

Wait for Postgres to be ready:
```bash
docker compose exec -T postgres pg_isready -U card_tool
```

## 3. Set up the Python environment (first time only)

```bash
python -m venv backend/.venv
backend/.venv/Scripts/python -m pip install --upgrade pip
backend/.venv/Scripts/python -m pip install -r backend/requirements.txt
cp backend/.env.example backend/.env   # then edit as in step 1
```

## 4. Run migrations

```bash
backend/.venv/Scripts/python -c "import os; os.chdir('backend'); from alembic.config import main; main(argv=['upgrade', 'head'])"
```

## 5. Seed a user to log in as

```bash
cd backend
../backend/.venv/Scripts/python scripts/seed_users.py "Astral" admin
cd ..
```

The login passcode is whatever `APP_PASSCODE` is set to in `backend/.env`
(defaults to `change-me`).

## 6. Start the API server

Both the API server and the Celery worker need their working directory to
be `backend/` (so `app.main` / `app.celery_app` resolve). In one
terminal:
```bash
cd backend
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

Confirm it's up (from the project root, or any terminal):
```bash
curl http://localhost:8000/api/health
```

## 7. Start a Celery worker

In a second terminal (Windows needs the `solo` pool — the default
`prefork` pool doesn't work there):
```bash
cd backend
.venv/Scripts/celery -A app.celery_app worker --loglevel=info --pool=solo
```
(On macOS/Linux you can drop `--pool=solo`.)

Watch this terminal's output as you upload a batch — you'll see
`extract_batch`, `crop_scan`, `hash_crop`, and `find_duplicates` tasks
fire.

## 8. Prepare a real test zip

Zip up real card scans using the client's naming convention:
```
{card_id}-front.jpg
{card_id}-back.jpg
```
Any `card_id` works as long as front/back share the same prefix, e.g.:
```
0001-front.jpg
0001-back.jpg
0002-front.jpg
0002-back.jpg
```
Zip them into `test-batch.zip` (any zip tool works; files can be nested in
a folder inside the zip, that's fine).

To deliberately test the duplicate-detection path, include the same
physical card twice under different `card_id` prefixes (e.g. scan it
once, rename, zip both copies in) — the pipeline should flag it as a
duplicate candidate even though the filenames differ.

## 9. Log in

```bash
curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"name": "YourName", "passcode": "change-me"}'
```
Copy the `access_token` from the response. Every command below needs it:
```bash
export TOKEN="paste-the-token-here"
```
(On Windows PowerShell: `$TOKEN = "paste-the-token-here"` and use
`-H "Authorization: Bearer $TOKEN"` the same way.)

## 10. Upload the batch

```bash
curl -s -X POST http://localhost:8000/api/batches \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@test-batch.zip" \
  -F "source_label=real data test"
```
Note the `batch_id` in the response.

Watch the Celery worker terminal — you should see `extract_batch` run,
followed by a `crop_scan` task per image.

## 11. Check batch/crop status

```bash
curl -s http://localhost:8000/api/batches/1 -H "Authorization: Bearer $TOKEN"
curl -s http://localhost:8000/api/batches/1/scans -H "Authorization: Bearer $TOKEN"
```
`scans` gives you a `thumbnail_url` per scan once it's cropped — open
those URLs in a browser to sanity-check crop quality. If a scan's status
comes back `crop_failed`, the aspect-ratio safety check rejected it (see
`aspect_ratio_tolerance` in `backend/app/config.py` — tune it here if real
scans are getting flagged too aggressively or not aggressively enough).

## 12. Walk the rotation review queue

Get the next pending pair (front + back shown together, per the spec):
```bash
curl -s "http://localhost:8000/api/review/rotation/next?batch_id=1" \
  -H "Authorization: Bearer $TOKEN"
```
This returns `front` and `back`, each with a `crop_id` and `image_url`.
Open the image URLs to see the actual crop.

If a card is upside down, rotate it (call once per side if both need it):
```bash
curl -s -X POST http://localhost:8000/api/review/rotation/12/rotate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"degrees": 180}'
```

Confirm the pair once both sides look right. Either crop ID identifies the
pair; the backend confirms both sides atomically and queues `hash_crop` for
the front (backs aren't hashed):
```bash
curl -s -X POST http://localhost:8000/api/review/rotation/12/confirm \
  -H "Authorization: Bearer $TOKEN"
```
Each `confirm` call returns the next pending pair, so you can loop this
by hand (or script it) until `next` returns `null`.

Check remaining queue size any time:
```bash
curl -s http://localhost:8000/api/review/rotation/queue-count \
  -H "Authorization: Bearer $TOKEN"
```

## 13. Walk the duplicate review queue

Once fronts are hashed, `find_duplicates` runs automatically. Check for
candidates:
```bash
curl -s http://localhost:8000/api/review/duplicates/next \
  -H "Authorization: Bearer $TOKEN"
```
This returns both crops' image URLs plus `structural_score` and
`color_score` — open both image URLs side by side to make the call
yourself, then:
```bash
curl -s -X POST http://localhost:8000/api/review/duplicates/1/decision \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status": "confirmed_duplicate"}'
```
or `{"status": "rejected"}`. The response gives you the next pending
candidate, same loop pattern as rotation review.

If nothing shows up here and you expected a duplicate, the thresholds in
`backend/app/config.py` (`structural_hash_max_distance`,
`color_sig_max_distance`) are the first thing to tune — see spec Section
11, these are explicitly meant to be adjusted against real data.

## 14. Browse the card log

```bash
# All cards in a batch
curl -s "http://localhost:8000/api/cards?batch_id=1" -H "Authorization: Bearer $TOKEN"

# Search by filename
curl -s "http://localhost:8000/api/cards?search=0001" -H "Authorization: Bearer $TOKEN"

# Full detail on one card, including duplicate history and hash values
curl -s http://localhost:8000/api/cards/12 -H "Authorization: Bearer $TOKEN"
```

## 15. Tear down

```bash
docker compose down
docker rm -f card-tool-minio   # if you used the MinIO option
```
(Postgres data persists in the `card-tool-v1_postgres_data` Docker
volume across `docker compose down`/`up`; add `-v` to `down` to wipe it
and start fresh.)


## Future Testing (when in development)

- You are now able to run scripts/dev.py to start the backend/frontend server.
- If using Windows Command Prompt and the script fails to start the server, **you may need to run `scripts/dev.py` as administrator** (right click the file and select "Run as administrator").
- This works great once you have configured the environment as per instructions inside this .md file.

## Troubleshooting

- **Celery worker never picks up tasks / hangs on Windows** — make sure
  you started it with `--pool=solo`.
- **`crop_failed` on everything** — check a raw scan's image directly
  (download via its `r2_key_raw`); if the background isn't near-black,
  Otsu thresholding may need a different approach for that scan set, or
  `aspect_ratio_tolerance` needs loosening.
- **No duplicate candidates ever appear** — lower
  `structural_hash_max_distance` / raise `color_sig_max_distance`
  temporarily to confirm the pipeline is wired correctly, then dial back
  in based on real false-positive/negative rates.
- **401 on every request** — tokens expire after `JWT_EXPIRES_MINUTES`
  (default 2 weeks); just log in again.
- **R2/MinIO connection errors** — double check `backend/.env` matches
  whichever option you picked in step 1; the two are mutually exclusive
  (`R2_ENDPOINT_URL` set = MinIO/local, unset = real R2 via
  `R2_ACCOUNT_ID`).
