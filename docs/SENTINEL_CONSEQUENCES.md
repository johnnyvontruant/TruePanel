# SENTINEL consequence summaries

SENTINEL consequence summaries make a proved blast radius easier to consume
without turning graph reachability into an outage claim.

The distinction is intentional. If an application is reachable from a failing
disk through proved storage and dataset relationships, SENTINEL may state that
the application is **in the proved consequence chain**. It may not state that
the application is down, interrupted, corrupt, or unavailable unless separate
evidence proves that condition.

## Contract

Each live Flight Director explanation may include a `consequences` object with:

- total proved-object count;
- proved storage-object count;
- application count;
- count of applications whose independently observed state is `RUNNING`;
- cargo count;
- backup-evidence count;
- the exact proved objects in each category;
- an explicit language guard.

The summary is a projection of `known_impact`. It cannot introduce an object
that was absent from the proved blast radius.

## Why application state is preserved

A storage dependency and a service outage are different facts.

For example, SENTINEL may prove:

```text
/dev/sdc -> raidz1-0 -> HDDs -> HDDs/Movies -> Radarr
```

while the TrueNAS application observation still reports Radarr as `RUNNING`.
Both facts are retained. SENTINEL does not rewrite `RUNNING` to `DEGRADED`
simply because the application depends on affected storage.

This supports a more useful operator statement:

> Radarr is in the proved storage consequence chain and is currently observed
> RUNNING.

It does **not** support:

> Radarr is unaffected.

and it does **not** support:

> Radarr is down.

Either stronger statement requires additional deterministic evidence.

## Safety boundary

Consequence summaries remain:

```text
read_only: true
control_authority: false
```

They do not create graph edges, modify application state, alter Pathfinder
recovery references, or change backup classification. They exist only to make
already-proved relationships easier for Mission Control and future presentation
layers to consume.
