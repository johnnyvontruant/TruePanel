
## Guarded lifecycle upgrade milestone

TruePanel completed its first live, same-version guarded upgrade promotion on
BattleStation.

The rehearsal:

- prepared and validated a compact sibling staging tree;
- preserved the deployed `truepanel.yaml` configuration;
- created and retained a timestamped sibling backup;
- promoted the validated stage into the deployed installation;
- restarted the LCD and Mission Control services;
- verified service state, Mission Control API availability, LCD transport,
  configuration continuity, package version, and startup restoration;
- completed with promotion state `promoted`, verification result `0`, and no
  rollback required.

This established the lifecycle path:

`stage -> backup -> promote -> restart -> verify -> retain rollback point`
