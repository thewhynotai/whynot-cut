#!/usr/bin/env bash
# onboard-new-client: builds the fictional workspace for this case (see ../_fixtures/example-clinic.sh).
here="${0//\\//}"
. "${here%/*}/../_fixtures/example-clinic.sh"
make_clinic dr-sherif no-profile
add_references dr-sherif
