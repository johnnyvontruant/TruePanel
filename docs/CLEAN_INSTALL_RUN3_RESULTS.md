# Clean-Install Validation: Run 3

## Result

**PASS**

Validated source commit:

`5772f0f1cf13fbeba05e0d0a475d8bfdf0995597`

Run 3 proved TruePanel through:

- a genuine blank-target fresh installation;
- safe generic fresh configuration;
- first LCD hardware startup;
- Mission Control activation;
- automatic Flight Deck rotation;
- physical front-panel button navigation;
- controlled LCD-service restart;
- full TrueNAS reboot;
- post-reboot LCD and button validation;
- native installed verification.

## Safety result

Final safety gates reported:

- motherboard fan control: **AUTOMATIC**;
- Host acceptance: **PASS**;
- standalone Host Agent: **inactive / static**;
- standalone activation marker: **absent**;
- standalone cutover: **DISABLED**.

The validated fresh buzzer configuration was:

`enabled = false`

`backend = pcspkr`

## PR #51 regression proof

Unsupported buzzer-backend warnings:

- pre-fix generation: **5**;
- corrected fresh startup: **0**;
- controlled LCD restart: **0**;
- full reboot: **0**;
- final post-reboot physical test: **0**.

## LCD proof

The fresh reader reported:

- connected: true;
- healthy: true;
- `/dev/ttyS1` at 1200 baud;
- reader errors: 0;
- callback errors: 0.

Physical button navigation passed before restart, after restart, and
after the full machine reboot.

The post-reboot reader began with zero button reports. One physical
navigation-button action increased the report count and populated
`last_button_time`.

## Validation-harness lessons

The canonical successful installer banner is:

`TruePanel Install Complete`

`truepanel verify` is an operational verifier and should run only after
the LCD and Mission Control services have been intentionally activated.

LCD reader-status fields live beneath the `reader` mapping rather than
at the top level of the status document.

## Lifecycle observation

During full reboot validation, the application services experienced an
early automatic stop/start cycle while the existing TrueNAS POSTINIT
restoration path was present.

The final boot generation was healthy and every safety, ownership,
runtime, API, physical-hardware, and verification gate passed. The
cycle is therefore retained as lifecycle-polish evidence rather than a
Run 3 failure.

## Graduation verdict

**RUN 3 CLEAN INSTALL GRADUATION = PASS**
