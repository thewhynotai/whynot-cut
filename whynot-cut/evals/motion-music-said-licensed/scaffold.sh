#!/usr/bin/env bash
# motion-music-said-licensed: builds the fictional workspace for this case (see ../_fixtures/example-clinic.sh).
here="${0//\\//}"
. "${here%/*}/../_fixtures/example-clinic.sh"
make_clinic example-clinic
add_episode_plan example-clinic
add_motion_project example-clinic EP12_R03_MO
