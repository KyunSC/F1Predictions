`suzuka-2025.jsonl` is a small reconstructed dashboard replay fixture, downloaded
2026-10-04 from Formula 1's official archive:
https://livetiming.formula1.com/static/2025/2025-04-06_Japanese_Grand_Prix/2025-04-06_Race/

It contains three unmodified compressed `Position.z` payloads from normalized
replay time 3598–3601 seconds, with SessionInfo, DriverList and TimingData states
reduced through time 3600 seconds as initial snapshots. The excerpt clock is
rebased by 3598 seconds. These initial snapshots are reconstructed checkpoints,
not original receipt messages. Do not use this excerpt to measure network delay,
or timing/position synchronization before its checkpoint. Full downloads remain
in gitignored `cache/`. No prediction notebook data is involved.
