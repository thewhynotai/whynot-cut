//! The ACL end to end on the mock runtime (review L3): build.rs declares an app manifest, so EVERY registered command
//! needs a capability grant. Without the manifest Tauri lets the local UI call any registered command, so removing
//! it must turn this test red. (An integration test: on Windows it needs the app manifest resource that build.rs
//! links into test binaries.)

/// Registered in the test app only, never granted: the app manifest (build.rs) must make the ACL refuse it.
#[tauri::command]
fn ungranted_probe() -> &'static str {
    "reached"
}

fn mock_invoke(webview: &tauri::WebviewWindow<tauri::test::MockRuntime>, cmd: &str)
    -> Result<tauri::ipc::InvokeResponseBody, serde_json::Value> {
    tauri::test::get_ipc_response(
        webview,
        tauri::webview::InvokeRequest {
            cmd: cmd.into(),
            callback: tauri::ipc::CallbackFn(0),
            error: tauri::ipc::CallbackFn(1),
            url: if cfg!(windows) { "http://tauri.localhost" } else { "tauri://localhost" }.parse().unwrap(),
            body: tauri::ipc::InvokeBody::default(),
            headers: Default::default(),
            invoke_key: tauri::test::INVOKE_KEY.to_string(),
        },
    )
}

#[test]
fn a_registered_but_ungranted_command_is_refused_end_to_end() {
    let ctx: tauri::Context<tauri::test::MockRuntime> = tauri::generate_context!();
    let app = tauri::test::mock_builder()
        .invoke_handler(tauri::generate_handler![whynot_cut_setup_lib::commands::app_info, ungranted_probe])
        .build(ctx)
        .unwrap();
    let main = tauri::WebviewWindowBuilder::new(&app, "main", Default::default()).build().unwrap();
    let info = whynot_cut_setup_lib::app_info_for(false);
    let got = mock_invoke(&main, "app_info").expect("app_info is granted").deserialize::<serde_json::Value>().unwrap();
    assert_eq!(got["version"], info.version);
    let refused = mock_invoke(&main, "ungranted_probe").expect_err("an ungranted command must be refused");
    assert!(refused.to_string().contains("not allowed"), "{refused}");
    // and a granted command from another window is refused too (the capability names only `main`)
    let other = tauri::WebviewWindowBuilder::new(&app, "other", Default::default()).build().unwrap();
    assert!(mock_invoke(&other, "app_info").is_err());
}
