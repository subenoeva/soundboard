# Changelog

## [0.4.7](https://github.com/subenoeva/soundboard/compare/v0.4.6...v0.4.7) (2026-08-02)


### Bug Fixes

* **audio:** absorb bursty input callbacks ([#32](https://github.com/subenoeva/soundboard/issues/32)) ([1619947](https://github.com/subenoeva/soundboard/commit/161994747caca8d975d3354261c9bd962e8cb7a0))

## [0.4.6](https://github.com/subenoeva/soundboard/compare/v0.4.5...v0.4.6) (2026-08-01)


### Bug Fixes

* build the AppImage against the full set of libraries it bundles ([#30](https://github.com/subenoeva/soundboard/issues/30)) ([2ed38c3](https://github.com/subenoeva/soundboard/commit/2ed38c33926176af18416e4e4e765bf7ec734df2))

## [0.4.5](https://github.com/subenoeva/soundboard/compare/v0.4.4...v0.4.5) (2026-08-01)


### Bug Fixes

* **ci:** install the X11 libraries Qt's xcb plugin needs to start ([#27](https://github.com/subenoeva/soundboard/issues/27)) ([f98f7b2](https://github.com/subenoeva/soundboard/commit/f98f7b2167889432b5d122c6f2fcaf7e9346c7fb))

## [0.4.4](https://github.com/subenoeva/soundboard/compare/v0.4.3...v0.4.4) (2026-08-01)


### Bug Fixes

* prune the Qt plugins Linux left orphaned ([#25](https://github.com/subenoeva/soundboard/issues/25)) ([8b5a63e](https://github.com/subenoeva/soundboard/commit/8b5a63e72c70dba57c8592f374e0b7908e7fb2b5))

## [0.4.3](https://github.com/subenoeva/soundboard/compare/v0.4.2...v0.4.3) (2026-08-01)


### Bug Fixes

* bundle pynput's X11 backend in the AppImage ([#23](https://github.com/subenoeva/soundboard/issues/23)) ([779074f](https://github.com/subenoeva/soundboard/commit/779074f5a106cc775fc3d3372be354bb8be62e9b))

## [0.4.2](https://github.com/subenoeva/soundboard/compare/v0.4.1...v0.4.2) (2026-08-01)


### Bug Fixes

* drop Qt plugins left without their pruned library ([#21](https://github.com/subenoeva/soundboard/issues/21)) ([c643136](https://github.com/subenoeva/soundboard/commit/c643136553aacd18850e18c33f9cf8f333be4225))

## [0.4.1](https://github.com/subenoeva/soundboard/compare/v0.4.0...v0.4.1) (2026-08-01)


### Miscellaneous Chores

* release 0.4.1 ([#18](https://github.com/subenoeva/soundboard/issues/18)) ([0f878ca](https://github.com/subenoeva/soundboard/commit/0f878cab57d2bbff81279e010916a35f13d64e8a))

## [0.4.0](https://github.com/subenoeva/soundboard/compare/v0.3.0...v0.4.0) (2026-07-31)


### Features

* **updater:** self-update from signed GitHub releases ([#15](https://github.com/subenoeva/soundboard/issues/15)) ([395c601](https://github.com/subenoeva/soundboard/commit/395c601ed6b3a80d1d25160f6bea2ba5bf18940d))

## [0.3.0](https://github.com/subenoeva/soundboard/compare/v0.2.2...v0.3.0) (2026-07-31)


### Features

* **ui:** rebuild the desktop GUI on Qt Quick ([608baa6](https://github.com/subenoeva/soundboard/commit/608baa68d9b2479b31beafc339abe05640c1a9bd))

## [0.2.2](https://github.com/subenoeva/soundboard/compare/v0.2.1...v0.2.2) (2026-07-31)


### Bug Fixes

* fall back to login when a stored session fails to restore ([#10](https://github.com/subenoeva/soundboard/issues/10)) ([f969ec7](https://github.com/subenoeva/soundboard/commit/f969ec70e155a550f231676ecd92837afb324333))

## [0.2.1](https://github.com/subenoeva/soundboard/compare/v0.2.0...v0.2.1) (2026-07-31)


### Bug Fixes

* bundle pynput's platform backend and survive a missing keyring daemon ([#8](https://github.com/subenoeva/soundboard/issues/8)) ([406e62e](https://github.com/subenoeva/soundboard/commit/406e62e4b53e7221fd8335b3a2e368b55680671c))

## [0.2.0](https://github.com/subenoeva/soundboard/compare/v0.1.0...v0.2.0) (2026-07-30)


### Features

* add ClipButton with idle/loading/playing states and file drop ([45a0fec](https://github.com/subenoeva/soundboard/commit/45a0fec012a9153cd20bed7f93fe18c1b11f614a))
* add ClipGrid wiring click/drop/context-menu signals ([01249ef](https://github.com/subenoeva/soundboard/commit/01249ef1532ffbf1a1e7fbff849b0c62a622c990))
* add DeviceSettingsDialog for mic/out/grid-size selection ([89c6c94](https://github.com/subenoeva/soundboard/commit/89c6c9425a3b230975a86d38da46098415587d2b))
* add DownloadWorker to resolve remote PCM off the Qt thread ([403870b](https://github.com/subenoeva/soundboard/commit/403870b9bfdf11fd454d5e4cc96aca03d485db97))
* add global hotkey manager over pynput, with a fake for tests ([3486024](https://github.com/subenoeva/soundboard/commit/3486024f7b2e10cbeace9af26e9803cae134b0fa))
* add gui subcommand, lazily importing the PySide6 window ([8bc6d35](https://github.com/subenoeva/soundboard/commit/8bc6d35dfb9eb572a54dca47769b661a60474e6d))
* add LoginDialog for inline Supabase signup/login ([56dff46](https://github.com/subenoeva/soundboard/commit/56dff464712fa25a3ae1163337397ce5a1a5fbc7))
* add MainWindow wiring grid, hotkeys and remote downloads to the engine ([677e7b4](https://github.com/subenoeva/soundboard/commit/677e7b4e8afa629c47988a62746575151316e745))
* add run_gui entry point orchestrating session, layout and devices ([237d08f](https://github.com/subenoeva/soundboard/commit/237d08fbce54e4d45499a704237f5c4b3b2f11aa))
* add system tray icon with show/quit actions ([7a5e004](https://github.com/subenoeva/soundboard/commit/7a5e0049c0d81c55b4ab2b53cce34cd883cbf489))
* add ui grid layout model and JSON persistence ([f4492e4](https://github.com/subenoeva/soundboard/commit/f4492e468ae85f9cfd37c882a8c8587acb148ae3))
* **audio:** add AudioBackend protocol and deterministic fake backend ([bf833b2](https://github.com/subenoeva/soundboard/commit/bf833b26e1cda1cef3b533d3aca96e3d8b139fcb))
* **audio:** add AudioEngine wiring capture, drift correction and mixing ([82166ba](https://github.com/subenoeva/soundboard/commit/82166ba04f2ecb05d9adb81a84e78fdba760a46a))
* **audio:** add clock-drift controller and fractional-rate resampler ([ff36d0f](https://github.com/subenoeva/soundboard/commit/ff36d0f81c20610f09c8667de86597998a665fdf))
* **audio:** add mixer with ducking and soft limiter ([2345852](https://github.com/subenoeva/soundboard/commit/2345852fa04dcac5ab719be5d81059417eff5d62))
* **audio:** add PortAudio backend with name-based device lookup ([dde52ce](https://github.com/subenoeva/soundboard/commit/dde52cea7bab1df78fb1557d01f9e4c0c5a86fef))
* **audio:** add SPSC ring buffer with overrun and underrun accounting ([ac0f334](https://github.com/subenoeva/soundboard/commit/ac0f3341989a1e151afa5af698eb5bf8eb31962b))
* **audio:** add Voice with trim, gain and looping ([0fc8579](https://github.com/subenoeva/soundboard/commit/0fc857967c9ea0b90a9c2c86cecf6ac653af195d))
* **cli:** add auth/sounds/categories subcommands and remote --sound resolution ([13e37e5](https://github.com/subenoeva/soundboard/commit/13e37e5f561c399c5dbff1bb3fce930678a40580))
* **cli:** add devices listing and engine runner ([607632a](https://github.com/subenoeva/soundboard/commit/607632a6bf394c7ba593ee0437c1453398e26a15))
* **db:** add sounds/categories/profiles schema with RLS and integration tests ([af76fd2](https://github.com/subenoeva/soundboard/commit/af76fd250da63c9e02ef1fb3ef457bdde267afd1))
* fall back to baked-in Supabase defaults when unconfigured ([e602e9b](https://github.com/subenoeva/soundboard/commit/e602e9bde98c6bf53358284e33f32a2971558cb0))
* **library:** add importer with sha256 dedup key and ceiling-relative gain ([7558b40](https://github.com/subenoeva/soundboard/commit/7558b40f8ec7cfef3a86f29dc089bcf988840693))
* **library:** add sha256-keyed playback cache with corruption recovery ([f538b4d](https://github.com/subenoeva/soundboard/commit/f538b4d5c1ec8109119145707ba06e461b8b10d6))
* PySide6 desktop GUI (clip grid, tray, global hotkeys) ([d0ab0a9](https://github.com/subenoeva/soundboard/commit/d0ab0a9556356193041fec241772984960537d80))
* **remote:** add category CRUD with creator-checked delete ([5317d66](https://github.com/subenoeva/soundboard/commit/5317d664ada39202a25d297c8dd7bea4b89330d5))
* **remote:** add in-memory FakeRemoteClient for tests ([a950302](https://github.com/subenoeva/soundboard/commit/a9503023b831440e44930792742677a14487b20f))
* **remote:** add Session/Sound/Category/Profile models and RemoteClient protocol ([52624f3](https://github.com/subenoeva/soundboard/commit/52624f39ba4d1223efbbd9745a7afcfdf1606958))
* **remote:** add SessionStore, config resolution and SupabaseRemoteClient ([07966ec](https://github.com/subenoeva/soundboard/commit/07966ec3a1f3a62d7131da06fd3cbacca1fc91d1))
* **remote:** add signup/login/logout with first-login profile bootstrap ([dae0953](https://github.com/subenoeva/soundboard/commit/dae0953883abd0a251918d009787ba9150d9b173))
* **remote:** add sound CRUD with owner-checked edit/delete and cache resolution ([4d24e04](https://github.com/subenoeva/soundboard/commit/4d24e04be2dc91faccfdcf46c762499e42d51888))


### Bug Fixes

* **audio:** close the output stream leak on AudioEngine.start() failure ([9312d83](https://github.com/subenoeva/soundboard/commit/9312d8334ad1e8cc86ed7a4c037682ff52053df1))
* **audio:** close the RingBuffer lost-update race ([cfee904](https://github.com/subenoeva/soundboard/commit/cfee904271fffe9fa99ad365e2d26fc0728dcb03))
* **audio:** resolve device-name ties by preferring WASAPI ([d6eb79d](https://github.com/subenoeva/soundboard/commit/d6eb79dd68dca461d4b7ecc9c2527434533f8a68))
* **audio:** stop AudioEngine.start() leaking the input stream on failure ([99c156e](https://github.com/subenoeva/soundboard/commit/99c156e2ff80d1c5fa8964962ab7dafd3f309321))
* clean up temp dirs and tolerate find failures in build_appimage.sh ([6c0d308](https://github.com/subenoeva/soundboard/commit/6c0d308f8650131e3ae0ff90dbaedcf4f9493745))
* **cli:** handle setup errors, add a backend seam, and surface driver xruns ([d3b13db](https://github.com/subenoeva/soundboard/commit/d3b13db3bafeed2c86613498d5d4893703cd4d1f))
* contain QMimeData lifetime workaround locally in test_clip_button.py ([669b9d2](https://github.com/subenoeva/soundboard/commit/669b9d2c201a07e07ca92ba37a9765d790dd7479))
* **db:** grant table privileges to authenticated and allow content-addressed re-uploads ([05f5d1c](https://github.com/subenoeva/soundboard/commit/05f5d1c42f33cdacf6aeaa3985017615004bb9eb))
* default to the gui subcommand when invoked with no arguments ([17b958a](https://github.com/subenoeva/soundboard/commit/17b958a934dfacb7529314fb6ce5b90d3d37e024))
* match Engine protocol's play() to AudioEngine's keyword-only signature ([424e9b8](https://github.com/subenoeva/soundboard/commit/424e9b85ae362f739cf6737671e9404a23c2fbda))
* point find_library at the PortAudio bundled in the AppImage ([d32186d](https://github.com/subenoeva/soundboard/commit/d32186dc5d35804a7dc6cf36b6f428c7322cbfb0))
* run Linux CI tests under Xvfb ([#5](https://github.com/subenoeva/soundboard/issues/5)) ([8e3ff05](https://github.com/subenoeva/soundboard/commit/8e3ff054733b9232abfee67de04e50ca19d08ece))
* show a dialog when the remote client cannot be built ([bdb8a42](https://github.com/subenoeva/soundboard/commit/bdb8a4246e201c0b2be4a180bf63b4a92cf52035))
