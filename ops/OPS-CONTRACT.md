# Novel engineering maintenance

Owner authorization: diagnose and repair Novel engineering failures, delegate to
the configured Codex cloud environment, test and deploy routine repairs. Preserve
the original books, tasks, attempts, uploads, checkpoints and all history.
Do not change literary review standards, author decisions, permissions, database
schema, model execution policy or this maintenance service through this API.
Those changes need a separately reviewed operator change.

Use the operator-configured `NOVEL_OPS_URL` HTTPS entry ending in `/novel-ops/v1`.
Keep its deployment hostname and configuration in the private environment.
Use `Authorization: Bearer ${NOVEL_OPS_TOKEN}` from the environment's network
secret. Never print it, put it in a URL, copy auth files, or upload the book root.
The token authorizes source read and bounded release operations only.

1. GET `/status`. Record the exact `source_sha256` and runtime source identity.
   Read active creative tasks through the existing `novel_work_status` tool.
2. GET `/source.zip`. It contains the matching code and engineering fixtures,
   without the book root, runtime databases or credentials.
3. Fix a copy, retain existing fixes and tests, add meaningful regression coverage.
   A completed cloud task or passing local test is not a deployment receipt.
4. POST `/releases` with JSON:
   `{"request_id":"unique-lowercase-id","base_sha256":"from status","reason":"problem and fix","files":{"novel/example.py":"full UTF-8 source","tests/test_example.py":"full UTF-8 source"}}`.
   Only Python files directly under novel/ and tests/test_*.py are allowed.
   No deletes, shell commands, arbitrary destinations or business-data paths.
   The same ID with identical parameters returns the original receipt.
   The service refreshes the release's auxiliary snapshots of its operator-owned
   maintenance.py and api_runner.py and records their hashes in the receipt.
   Callers still cannot edit those files or change the running maintenance service.
5. POST `/releases/<id>/validate` with `{}`. This returns 202. GET the release
   receipt with bounded waits until `validated` or `failed`. Tests run in a
   disposable Linux service without network or access to the live book root.
   The expanded full suite has a bounded 600-second runtime; CPU, memory,
   network isolation and all test assertions remain enforced.
6. After checking the diff stays within the standing authorization, POST
   `/releases/<id>/deploy` with `{}`. Deployment starts the other API slot,
   verifies its identity and authentication, and gracefully switches the proxy.
   The old service drains. Failed switching restores the previous route.
   Exception for a completed request: if that release receipt is already in
   `state=deployed`, the handler returns the existing saved receipt immediately.
   It does not validate, start or stop services, switch routes, update files,
   change the receipt timestamp, or write business data. This is an idempotent
   replay, not a new deployment. First read the release and `/status` to establish
   that the receipt is deployed and its source hash matches the current runtime;
   otherwise an old receipt is only historical evidence, not current state.
7. GET the release and `/status`; verify `deployed`, runtime hash and actual
   authenticated Novel MCP calls. Continue the original Dot task only after
   state readback. If a write result is unclear, inspect its persisted request;
   never blindly replay a failed finish ID or recreate the book task.

GET `/releases/<id>` is the durable receipt. An interrupted release does not
auto-resume. Diagnose first. POST `/rollback` with
`{"expected_sha256":"currently deployed hash"}` switches to retained previous
code. It never rolls back books or databases.

Creative execution remains Dot-native. Codex is only the engineering maintainer.
Use the same engineering incident thread for follow-ups; preserve error evidence.
Do not start monitoring schedules or duplicate active work as part of a repair.
