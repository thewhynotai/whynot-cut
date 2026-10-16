// WhyNot Cut Setup entry point. Release builds have no console window on Windows.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    whynot_cut_setup_lib::run();
}
