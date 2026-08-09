# CS2 Radar backend

Radar uses only Steam's public Web API. It does not connect to the CS2 Game
Coordinator and cannot reliably expose Premier rank, CS profile level, service
medals, queue state, map, or premade-party membership.

## Configuration

Copy `.env.example` to `.env` and set at least:

- `STEAM_API_KEY`: Steam Web API user key.
- `JWT_SECRET`: a long random value shared by all API workers.
- `BASE_URL`: public HTTPS API origin used for the Steam OpenID callback.
- `WEB_ORIGIN`: allowed Web application origin and OpenID redirect target.

The previously tracked `.env` was removed from the repository. Rotate every
credential that has appeared in Git history before deploying this branch.

## Database migration

Run `migrations/20260810_radar_up.sql` against the TrashBox MySQL database
before starting the Radar-enabled API. The migration adds only Radar and Web
login tables. To roll the feature back, stop the Radar-enabled API and run
`migrations/20260810_radar_down.sql`.

## Runtime behavior

- Opening a Radar client requests one snapshot; snapshots within 15 seconds
  reuse the latest result.
- Presence and ban calls use batches of at most 100 IDs with three concurrent
  Steam requests.
- A continuous session lasts at most ten minutes and scans every 20 seconds.
- CS2 playtime is refreshed for up to 30 stale users per tick and otherwise
  reused for 24 hours, so a large new watchlist is enriched gradually.
- A shared watchlist supports at most 2,000 Steam accounts.

Run tests from `Backend`:

```sh
pytest -q tests
```
