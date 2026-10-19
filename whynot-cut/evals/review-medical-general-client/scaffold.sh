#!/usr/bin/env bash
# review-medical-general-client: builds the fictional workspace for this case (see ../_fixtures/example-clinic.sh): a clip whose
# plan is compiled and waits for the content review (plant/ = its plan, review-scan output and transcript).
here="${0//\\//}"
. "${here%/*}/../_fixtures/example-clinic.sh"
make_clinic example-coach
add_review_case example-coach C0302 "${here%/*}"
