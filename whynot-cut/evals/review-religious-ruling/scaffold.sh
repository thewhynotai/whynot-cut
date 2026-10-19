#!/usr/bin/env bash
# review-religious-ruling: builds the fictional workspace for this case (see ../_fixtures/example-clinic.sh): a clip whose
# plan is compiled and waits for the content review (plant/ = its plan, review-scan output and transcript).
here="${0//\\//}"
. "${here%/*}/../_fixtures/example-clinic.sh"
make_clinic example-talks
add_review_case example-talks C0306 "${here%/*}"
