# Host timing results and evidence boundary

Three process sessions on the available Apple M5 Pro Mac completed all 192
measured requests and all 24 planned warm-ups. The largest measured full-service
roundtrip was 653.585 ms; none exceeded the one-second service budget.
Every raw sample and warm-up is retained. The 162 definite outputs passed their
prespecified after-timing fixed-output checks. Unresolved results remain
unresolved and are not credited as physical interventions.

Of the 192 measured input instances, 108 declare zero time from their modeled
measurement to application. Any positive measured service latency precludes a
literal implementation of that zero-delay pattern through this request path.
This is a timing-assumption diagnostic, not an observed physical violation.
The other application windows still require unmeasured sensor, actuator and
clock-alignment bounds. The earlier protected endpoints remain unchanged.

The clock reports mach_absolute_time with approximately 41.67 ns resolution.
This is not calibrated absolute accuracy. Back-to-back diagnostics, method order,
startup costs, raw CPU/elapsed times and per-session host load/power are retained.
Three process sessions on one device/day are not independent hardware sessions.
No observed maximum is a worst-case bound. Barrier latency includes frequent
abstentions; it must not be used as evidence of superior protective throughput.

Only host timing and virtual-interface checks were achieved. No target processor
in the loop, real sensor/actuator interface, physical cart trial, human review or
external laboratory replication was obtained. The physical configuration is
intentionally unapproved, and the code contains no physical actuator backend.

A compact local reviewer bundle reproduced 738 previously recorded cart command
and dual checks in a fresh standard-library environment. This checks bundle
usability and numerical reproduction, not independent human review. The original
spacecraft campaign, cart transfer and failed attempt remain unchanged.
