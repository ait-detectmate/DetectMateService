# Federated Learning

Several detectors, each trained on its own data, can share what they learned through a central hub. The service supports the library's *stack later* approach: every node keeps its own state, and a hub merges it on request over the HTTP API. No shared memory is needed, so each node can run in its own container or on its own machine.

> **Note:** Federation needs DetectMateLibrary 0.6.1 or later. In 0.6.1 detectors can export, stack and aggregate, but none can adopt a merged binary yet; see [Adopting the merged state](#adopting-the-merged-state).

## Enable federation

Set `allow_fed: true` in the detector config of every site and of the hub:

```yaml
detectors:
  NewValueDetector:
    method_type: new_value_detector
    allow_fed: true
    # ...
```

It cannot be switched on with `/api/v1/reconfigure`; restart the service after changing it. Not every detector supports federation; see the library documentation for which ones do.

## Running a federation round

The hub is a detector with the same config as the sites. It does not need to receive log data. A round looks like this (add `-H "X-Auth-Token: $KEY"` if an API key is set):

```bash
# 1. stop the engine on all nodes
curl -X POST http://site-a:8000/api/v1/stop      # repeat for every site and the hub

# 2. collect each site's state
curl http://site-a:8000/api/v1/federation/export -o site-a.bin
curl http://site-b:8000/api/v1/federation/export -o site-b.bin

# 3. stack it on the hub and aggregate
curl -X POST http://hub:8000/api/v1/federation/stack -F "files=@site-a.bin" -F "files=@site-b.bin"
curl -X POST http://hub:8000/api/v1/federation/aggregate -o global.bin

# 4. send the merged state back to every site and restart
curl -X POST http://site-a:8000/api/v1/federation/adopt -F "file=@global.bin"
curl -X POST http://site-a:8000/api/v1/start
```

### Adopting the merged state

`/api/v1/federation/adopt` calls the detector's `load_binary()`. The library has a default `load_binary()` that only logs a warning and changes nothing, so the endpoint returns `501` for any detector that does not override it (in 0.6.1, none do) instead of reporting a success that did nothing. Until it is supported, give each site the hub's learned state instead. After aggregating, the hub holds the merged state:

```bash
curl http://hub:8000/api/v1/persistency/export -o hub_state.zip
curl -X POST http://site-a:8000/api/v1/persistency/import -F "file=@hub_state.zip"
```

When no further rounds are planned, call `/api/v1/federation/finalize` on each node to remove the files federation keeps on disk. This is permanent: the node cannot export, stack or aggregate afterwards.

## Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/v1/federation/status` | Whether federation is enabled, how many peers are stacked, number of aggregations, time of the last one, and whether it was finalized. |
| `GET` | `/api/v1/federation/export` | Downloads this node's federation binary. |
| `POST` | `/api/v1/federation/stack` | Uploads one or more peer binaries (`files` form field, repeatable) for the next aggregation. |
| `POST` | `/api/v1/federation/aggregate` | Merges the stacked peers into this node and returns the merged binary. `?unstack=false` keeps the peers stacked. |
| `POST` | `/api/v1/federation/adopt` | Replaces this node's learned state with a merged binary (`file` form field). |
| `POST` | `/api/v1/federation/finalize` | Ends federation for this node and removes its federation files. |

All endpoints except `status` return:

- `404` if no library component is loaded
- `409` if `allow_fed` is not set, federation was finalized, or the engine is running (stop it with `/api/v1/stop` first)
- `422` if an uploaded binary is empty or invalid

`/api/v1/federation/aggregate` also returns `409` when nothing is stacked, and `/api/v1/federation/adopt` returns `501` when the detector does not implement `load_binary()`.

## Demo

[`demo/federation`](https://github.com/ait-detectmate/DetectMateService/tree/main/demo/federation) runs three sites and a hub with Docker Compose and shows a site that stops alerting on users another site already knows. See its README for the steps.
