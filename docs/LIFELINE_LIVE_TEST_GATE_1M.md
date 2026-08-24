# Project Lifeline Live Test Gate 1M

## Scope

Gate 1M certifies TruePanel's guarded upgrade promotion and automatic rollback engine using disposable clones of the live BattleStation deployment.

No live deployment tree replacement, production service restart, real `/var/lib` write, hardware action, or storage mutation is performed by this gate.

## Certified source

- branch: `feature/project-lifeline`
- source head before this documentation commit: `027d02842b3ccbf266f6aa706fab0eb79febda52`
- source version: `1.2.0`
- deployed production generation used as rehearsal baseline: `1.2.0rc3`

## Gate 1M initial rehearsal

The initial Gate 1M run proved the successful-promotion half of the lifecycle:

- a validated upgrade stage was created with the real `prepare_stage()` engine
- the wrong promotion confirmation was rejected before backup, restart, verification, or deployment mutation
- confirmation `PROMOTE_TRUEPANEL` allowed promotion of a disposable production clone
- an injected restart callback and verifier were called exactly once
- the promoted clone verified as the Lifeline generation
- a retained promotion backup and backup receipt were created
- `truepanel.yaml` remained preserved
- the upgrade manifest reached `state: promoted`

The run then held in an independent test-harness assertion after `PROMOTION VERIFIED`. Production remained untouched.

## Harness findings

Two independent comparison issues were identified and closed without changing the upgrade engine:

1. The first custom digest included `*.before-*` files that TruePanel's upgrade contract intentionally excludes. BattleStation contained examples including `truepanel.yaml.before-fan-channel-metadata` and `truepanel/web/static/index.html.before-lcd-refresh`.
2. The first engine-native rsync comparison reported only `.d..t...... ./`, representing root-directory timestamp drift rather than managed file content drift.

The final comparator therefore used TruePanel's own promotion exclusions together with:

- `--checksum` to compare actual file contents
- `--omit-dir-times` to ignore non-semantic directory mtime noise

No production behavior was changed to satisfy the harness.

## Gate 1M-R2 final certification

Gate 1M-R2 passed.

### Successful promotion revalidation

The retained successful-promotion artifacts from Gate 1M were independently revalidated:

- backup vs live old-generation managed tree: empty checksum-based rsync delta
- promoted clone vs validated Lifeline stage: empty checksum-based rsync delta
- source version: `1.2.0`
- old deployed version: `1.2.0rc3`
- promotion manifest remained `state: promoted`
- `promotion_performed: true`
- `verification_result: 0`
- `rollback_performed: false`
- retained backup receipt validated as `kind: promotion`, `state: retained`
- configuration remained immutable

### Automatic rollback flight

A fresh disposable clone of production RC3 was created and verified to match the live old generation under the checksum-based engine contract.

A fresh Lifeline stage was created with the real staging engine and validated successfully.

Promotion was then executed with the real guarded promotion engine and injected non-systemd callbacks:

1. simulated restart of promoted disposable clone
2. verifier confirmed the promoted clone matched the Lifeline stage
3. verifier intentionally returned code `73`
4. TruePanel reported that verification failed and started automatic rollback
5. retained pre-promotion backup was restored
6. simulated restart of restored disposable clone
7. second verifier confirmed the restored tree matched live RC3 with an empty checksum-based rsync delta
8. TruePanel reported `ROLLBACK VERIFIED`

The guarded promotion call intentionally returned `1`, indicating failed promoted-generation verification followed by a successful automatic rollback.

### Final rollback manifest

The final rollback-test manifest recorded:

- `state: rolled_back`
- `promotion_performed: true`
- `services_modified: true`
- `verification_result: 73`
- `rollback_performed: true`
- deployed baseline version `1.2.0rc3`
- source version `1.2.0`

### Safety guards

After Gate 1M-R2:

- live upgrade asset namespace was unchanged
- real `/var/lib/truepanel/lifeline` remained absent
- production `truepanel.yaml` hash remained unchanged
- production LCD PID remained unchanged
- production Mission Control PID remained unchanged
- production Mission Control systemd unit hash remained unchanged
- `/var/lib/truepanel` metadata remained unchanged
- HDDs remained `ONLINE`
- all six RAIDZ1 leaves remained `ONLINE`
- no known data errors were reported
- no hardware action was performed
- no storage mutation was performed
- no storage authority was granted

## Result

**PASS: Gate 1M-R2**

The production-promotion rehearsal now proves both directions of the software lifecycle without modifying production:

- known-good RC3 clone -> validated Lifeline stage -> verified Lifeline promotion
- known-good RC3 clone -> Lifeline promotion -> forced verification failure -> automatic rollback -> exact managed-tree restoration of RC3

This certification does not authorize live promotion, production service restart, storage writes, or merge of PR #69.
