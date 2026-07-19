# TruePanel Roadmap

## Current platform

TruePanel currently provides:

- Mission Control and structured events
- Flight Deck and AutoPilot
- native A125 graphics and instruments
- pool, SMART, thermal, ZFS, and storage health monitoring
- physical TVS-671 bay fault indication
- historical telemetry
- plugin API v1
- hardware abstraction and command services
- Project Stargate laboratory and safety model
- native TrueNAS SCALE installation

## Path to 1.0

### Stability

- reconcile multiple simultaneous storage fault details on the LCD
- complete service restart and upgrade recovery tests
- harden configuration migration and validation
- add release-grade logging and diagnostics summaries
- define supported TrueNAS upgrade procedures

### User experience

- finalize dashboard page ordering and naming
- add screenshots and hardware photographs
- improve button navigation and acknowledgement flows
- provide configuration examples for quiet, tactical, and night modes
- expose clearer storage topology and bay labels

### Packaging

- add complete project metadata and console entry points
- define reproducible releases
- add changelog and release notes
- test clean installs from tagged archives
- document backup and rollback procedures

### Hardware

- keep TVS-671 as the verified reference platform
- create a formal model profile interface
- validate additional QNAP models through Stargate
- graduate status LED control only after production policy is defined
- expand fan and thermal support without unsafe writes

### Plugins

- publish stable capability contracts
- expand example plugins
- add compatibility checks and clearer isolation reports
- document versioning and migration rules

## Beyond 1.0

- remote status API
- richer historical analysis
- event export and notifications
- additional LCD and OLED backends
- declarative dashboard layouts
- community hardware profiles
- signed or verified plugin packages

## Guiding rule

New features should make the front panel more useful without making the appliance less trustworthy. Calm information, exact hardware control, and reproducible evidence remain the compass.
