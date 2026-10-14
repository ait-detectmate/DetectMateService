# Federation demo

Three site detectors and one hub, each in its own container. Every site learns a different set of users. One federation round over the HTTP API merges what they learned, so a site stops alerting on users another site has already seen, while users nobody has seen still alert.

| Container | Role | HTTP API on the host |
| :--- | :--- | :--- |
| `site-a` | NewValueDetector, learns `alice`, `bob` | `localhost:8101` |
| `site-b` | NewValueDetector, learns `carol`, `dave` | `localhost:8102` |
| `site-c` | NewValueDetector, learns `erin` | `localhost:8103` |
| `hub` | NewValueDetector, receives no log data, aggregates | `localhost:8104` |
| `controller` | Sends login events and runs the round ([`federation_demo.py`](federation_demo.py)) | - |

## Run it

From this directory:

```bash
docker compose up --build --abort-on-container-exit
```

The image uses the DetectMateLibrary version pinned in `uv.lock`. To try an unreleased library branch or tag instead, set `LIBRARY_REF`:

```bash
LIBRARY_REF=my-branch docker compose up --build --abort-on-container-exit
```

The API key defaults to `demo-key` (override with `DETECTMATE_HTTP_API_KEY`).

## What you should see

```
Before federation
  site-a  login carol    -> ALERT
  site-c  login alice    -> ALERT
  site-b  login mallory  -> ALERT

Federation round
  hub aggregated 3 sites
  ...

After federation
  site-a  login carol    -> no alert
  site-c  login alice    -> no alert
  site-b  login mallory  -> ALERT
```

`mallory` was never seen at any site, so it alerts both times.

## What the controller does

1. Puts each site into training with `/api/v1/training/state`, sends its users, and stops training.
2. Stops all nodes, downloads each site's state with `/api/v1/federation/export`, stacks it on the hub with `/api/v1/federation/stack` and merges it with `/api/v1/federation/aggregate`.
3. Sends the merged state to every site with `/api/v1/federation/adopt`. If the detector cannot load a federation binary yet (`501`, the case for every detector in library 0.6.1), it imports the hub's state with `/api/v1/persistency/export` and `/api/v1/persistency/import` instead.
4. Restarts the sites and repeats the checks.

See [docs/federation.md](../../docs/federation.md) for the endpoints.

## Clean up

```bash
docker compose down
```
