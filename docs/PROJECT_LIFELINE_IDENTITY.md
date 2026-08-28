# Project Lifeline Drive Identity

Project Lifeline must distinguish a physical drive from the Linux device name
currently assigned to it. `/dev/sda`, `/dev/sdc`, and similar names are runtime
addresses. They are not persistent hardware identity and may change after a
reboot, controller discovery-order change, or topology change.

## Identity hierarchy

Lifeline resolves drive identity from read-only evidence in this order:

1. WWN/WWID, cross-checked against current inventory evidence;
2. full serial plus model, cross-checked against current inventory evidence;
3. stable ZFS/member identity when a GUID or stable by-id/by-partuuid path is
   available;
4. conservative pool + VDEV + bay + model + serial-suffix correlation;
5. the current Linux device name only as a low-confidence legacy fallback.

WWNs and full serial numbers are converted to opaque SHA-256-derived tokens
before they enter the Lifeline ledger. Public Mission Control status exposes at
most the existing serial suffix plus the opaque identity token. Raw WWNs and
full serials are not written into the Lifeline session JSON.

## Runtime address versus identity

A session may contain both:

- `drive_identity`: the privacy-safe persistent physical identity decision;
- `current_device`: the Linux address currently assigned to that hardware;
- `device_history`: previously observed Linux addresses for the same incident.

A change such as `sdc -> sdd -> sda` therefore updates runtime history rather
than manufacturing three repair incidents.

## Legacy session migration

Existing active sessions created with device-name fault keys are migrated only
when independent physical evidence agrees. The migration requires the same
pool, VDEV, bay, serial suffix, compatible model, and compatible capacity when
capacity is available.

Migration is metadata-only:

- one canonical session remains active;
- matching aliases become `superseded` rather than being deleted;
- legacy session IDs and fault keys remain attached to the canonical record;
- device names are preserved as observation history;
- acknowledgement and service-authority context is taken only from the chosen
  canonical record and is never unioned from stale aliases;
- storage-write authority is not introduced or changed.

If strong physical identities conflict, Lifeline fails closed and keeps the
sessions separate even when the bay and model look similar.

## Identity confidence and promotion

Identity strength is monotonic for an active incident. A later high-confidence
WWN observation may promote a serial/correlated session to the stronger stable
key. A temporary loss of WWN visibility must not downgrade an established WWN
session back to serial, bay correlation, or an `sdX` key.

## Replacement boundary

Physical-drive identity and recovery-procedure identity are intentionally
separate concepts. A replacement disk has a new WWN and serial number, while
the existing repair procedure may continue because the logical recovery target
is the same pool member/bay service operation.

The current implementation uses stable physical identity to prevent duplicate
fault sessions. Replacement-media transition remains governed by Lifeline's
existing replacement validation and guarded recovery state machine.

## Safety boundary

This identity resolver is read-only. It reads inventory and udev metadata and
writes only TruePanel's private Lifeline metadata ledger. It cannot offline,
replace, wipe, partition, detach, or otherwise mutate storage.
