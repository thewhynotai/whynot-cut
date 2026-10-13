#!/usr/bin/env bash
# panel-approval-sessionstart: builds the fictional workspace for this case (see ../_fixtures/example-clinic.sh).
here="${0//\\//}"
. "${here%/*}/../_fixtures/example-clinic.sh"
make_clinic .
add_project . C0238
add_panel_approval . C0238
