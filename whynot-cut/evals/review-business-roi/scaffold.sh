#!/usr/bin/env bash
# review-business-roi: builds the fictional workspace for this case (see ../_fixtures/example-clinic.sh): a clip whose
# plan is compiled and waits for the content review (plant/ = its plan, review-scan output and transcript).
here="${0//\\//}"
. "${here%/*}/../_fixtures/example-clinic.sh"
make_clinic example-clinic
add_review_case example-clinic C0309 "${here%/*}"
