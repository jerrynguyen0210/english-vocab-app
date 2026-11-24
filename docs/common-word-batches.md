# Resumable Common practice

The Common tab starts or resumes an account-owned batch with
`POST /api/v1/common-words/batches`. The response includes a UUID, status, and
questions (without answer keys). Repeating this request returns the same queued,
generating, or unanswered ready batch. Once its questions have been answered,
a new request queues the next batch. Failed batches require an explicit retry.

The client reads `GET /api/v1/common-words/batches/{id}` every three seconds.
Questions appear automatically when the status becomes `ready`; `complete`
means every word in the shared bank has been learned. Leaving the tab or route
cancels client polling without cancelling generation. Returning resumes the
account's batch, including after an app restart. Ready batches return only
unanswered questions for words that have not been learned on another device.

After five minutes the client stops polling and offers **Check again**. This
resumes the existing batch. Individual HTTP requests retain the standard
15-second network timeout; network failures offer a manual retry, which also
resumes queued, generating, or unanswered ready work.

Generation runs in `python -m app.common_worker`, independently of the API.
Batch records survive API/worker restarts. Each claim has a lease of
`COMMON_WORDS_TIMEOUT_SECONDS + 60` seconds. Expired claims become `failed`;
retry assigns a new batch UUID, preventing an old worker from saving results.
Question persistence and the ready status commit in the same transaction.
Failures expose only fixed client messages. Polling requires ownership and
returns `Cache-Control: no-store`. Account erasure removes batch metadata.

## Deployment

Apply the forward migration `0023` before serving the new endpoints, and run the
new `common-worker` alongside the API. Both development and Jetson Compose
files include it; the backend deployment helper builds and starts it with the
other workers. For a non-container setup, start `python -m app.common_worker`
using the same backend configuration as the API. Without this worker, batches
remain queued and the client eventually offers **Check again**.

Deploy the backend before the client. The previous synchronous
`POST /api/v1/common-words/batch` endpoint remains available for older clients;
its requests are separate from the resumable queue. Existing questions generated
through that legacy endpoint are not retroactively grouped into batches.
