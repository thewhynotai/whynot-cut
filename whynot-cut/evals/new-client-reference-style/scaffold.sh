#!/usr/bin/env bash
# new-client-reference-style: builds the fictional workspace for this case (see ../_fixtures/example-clinic.sh).
here="${0//\\//}"
. "${here%/*}/../_fixtures/example-clinic.sh"
make_clinic example-clinic no-profile
add_references example-clinic
