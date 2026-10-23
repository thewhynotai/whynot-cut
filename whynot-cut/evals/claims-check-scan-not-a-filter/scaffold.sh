#!/usr/bin/env bash
# claims-check-scan-not-a-filter: builds the fictional workspace for this case (see ../_fixtures/example-clinic.sh).
here="${0//\\//}"
. "${here%/*}/../_fixtures/example-clinic.sh"
make_clinic example-clinic
add_project example-clinic C0238
