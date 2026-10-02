# Changelog

## [0.11.0](https://github.com/bigknoxy/janus/compare/v0.10.0...v0.11.0) (2026-10-02)


### Features

* complete the S1 calibration mechanism — consumption + external-corpus mode ([#67](https://github.com/bigknoxy/janus/issues/67)) ([4678bfd](https://github.com/bigknoxy/janus/commit/4678bfda8a60b80b6d9e1aad23bd32c98fc7fd22))


### Bug Fixes

* calibrate_s1 fits the gate's objective, not prediction loss ([#69](https://github.com/bigknoxy/janus/issues/69)) ([d2f6eb3](https://github.com/bigknoxy/janus/commit/d2f6eb3c8365b46331ca1dad6aae4c6d40316735))
* load-saturated runs exit clean, originals restored ([#48](https://github.com/bigknoxy/janus/issues/48)) ([80d34b2](https://github.com/bigknoxy/janus/commit/80d34b2486c43ce80aa416b228f2a6ceb8340658))
* monitor ledger watch compares the committed ledger, pings once per episode ([#68](https://github.com/bigknoxy/janus/issues/68)) ([5a3c7e0](https://github.com/bigknoxy/janus/commit/5a3c7e08c84fcd623f8ac5baae6980db9c340cb3))


### Documentation

* calibrate_s1 docstring describes the gate's objective and the HTTP/corpus usage ([#70](https://github.com/bigknoxy/janus/issues/70)) ([e371d44](https://github.com/bigknoxy/janus/commit/e371d4427e9ba727d5fc6898183b75d942e16ecc))
* external RESULTS — the escalation is structural, not a decider artifact ([#64](https://github.com/bigknoxy/janus/issues/64)) ([bba53de](https://github.com/bigknoxy/janus/commit/bba53de18409e96b55b33d5df01322372c871043))

## [0.10.0](https://github.com/bigknoxy/janus/compare/v0.9.0...v0.10.0) (2026-10-01)


### Features

* eval --python flag ([#56](https://github.com/bigknoxy/janus/issues/56)) ([12b2130](https://github.com/bigknoxy/janus/commit/12b21308954494127fa8e6914a3a48789d199d6b))
* infra rows get an asterisk on the Ledger ([#53](https://github.com/bigknoxy/janus/issues/53)) ([79daa1e](https://github.com/bigknoxy/janus/commit/79daa1edb4d5a0a1c4af7a229c38d6182684cd9e))
* JB-1 external-repo mining + miner scope fix ([#49](https://github.com/bigknoxy/janus/issues/49)) ([ecded9a](https://github.com/bigknoxy/janus/commit/ecded9a868c33a3fed282d79ed09c3cda7b62c71))
* JB-1 layout auto-detection ([#51](https://github.com/bigknoxy/janus/issues/51)) ([d610ac6](https://github.com/bigknoxy/janus/commit/d610ac661421113b592502c09587a16f6fbc6f4f))


### Bug Fixes

* miner survives huge parametrized fixture names ([#54](https://github.com/bigknoxy/janus/issues/54)) ([6c7d6cc](https://github.com/bigknoxy/janus/commit/6c7d6cc3b2ecfa70ee7e83da839feeaec49455bd))
* monitor false-alarm on untracked output ([#55](https://github.com/bigknoxy/janus/issues/55)) ([17dc2a5](https://github.com/bigknoxy/janus/commit/17dc2a55c4c4c042974fc2574dc50b5f6f256009))
* nightly eval corpus scope — exclude external/ and external_raw/ ([e3ddaa2](https://github.com/bigknoxy/janus/commit/e3ddaa29a73dbd2e2abcc7f302e0926a9358d701))


### Documentation

* curated external corpus ([#58](https://github.com/bigknoxy/janus/issues/58)) ([24fce4e](https://github.com/bigknoxy/janus/commit/24fce4ea3b817b0f77168df42fdaf31b78b688ae))
* external-corpus eval results ([#57](https://github.com/bigknoxy/janus/issues/57)) ([525630d](https://github.com/bigknoxy/janus/commit/525630db060502c57229d06d004c027b62dcc5cd))
* Ollama 0.35 drop-in S1 backend ([#59](https://github.com/bigknoxy/janus/issues/59)) ([4f77693](https://github.com/bigknoxy/janus/commit/4f776937c99b0b18ada8c4dd7f9363db25d6e62b))

## [0.9.0](https://github.com/bigknoxy/janus/compare/v0.8.0...v0.9.0) (2026-09-27)


### Features

* JB-2 ledger arbitration ([#47](https://github.com/bigknoxy/janus/issues/47)) ([066213f](https://github.com/bigknoxy/janus/commit/066213ffb2f2e3e0b991cdc89be663d55129e30b))
* JB-3 S1 patch-candidate ranking ([#42](https://github.com/bigknoxy/janus/issues/42)) ([462063e](https://github.com/bigknoxy/janus/commit/462063e0706a54d102714c425a15621c8a49d8e8))
* LoadGovernor + single-flight eval lock ([#45](https://github.com/bigknoxy/janus/issues/45)) ([3142d5b](https://github.com/bigknoxy/janus/commit/3142d5baed69acab3970fb965fbe50861fa94d04))
* miner v2 fixture splitting ([#38](https://github.com/bigknoxy/janus/issues/38)) ([ab3d63c](https://github.com/bigknoxy/janus/commit/ab3d63c0560a7a54aaa6126edf1215708d3963f3))


### Bug Fixes

* **eval:** conftest shim for mined fixtures ([#43](https://github.com/bigknoxy/janus/issues/43)) ([a1cc747](https://github.com/bigknoxy/janus/commit/a1cc7470e1bf5cabcaf23d5c4564028327cebb9c))
* miner prompt anchors + regen ([#30](https://github.com/bigknoxy/janus/issues/30)) ([e2b9196](https://github.com/bigknoxy/janus/commit/e2b919626a166024448f2eadb0d4f19e6c7c665a))
* miner prompts carry anchors ([#29](https://github.com/bigknoxy/janus/issues/29)) ([23a2a4e](https://github.com/bigknoxy/janus/commit/23a2a4ed673325858c8f52c2d1c865a18da33615))
* prefill-measured timeouts ([#35](https://github.com/bigknoxy/janus/issues/35)) ([5581e49](https://github.com/bigknoxy/janus/commit/5581e498370401a07e806ab8f889c8b4049b49e2))
* ruff drift ([#27](https://github.com/bigknoxy/janus/issues/27)) ([4d90575](https://github.com/bigknoxy/janus/commit/4d90575292b4928fd0fd0af1664a615721c08d56))

## [0.8.0](https://github.com/bigknoxy/janus/compare/v0.7.0...v0.8.0) (2026-09-26)


### Features

* git-history benchmark miner ([#25](https://github.com/bigknoxy/janus/issues/25)) ([e850b24](https://github.com/bigknoxy/janus/commit/e850b249dea0f8ad8b9cd10433227896d0334423))

## [0.7.0](https://github.com/bigknoxy/janus/compare/v0.6.0...v0.7.0) (2026-09-26)


### Features

* living Ledger + finetune corpus accumulator ([#23](https://github.com/bigknoxy/janus/issues/23)) ([8e43911](https://github.com/bigknoxy/janus/commit/8e43911f44db262e1149bf7c5338236f8d61a3d2))


### Bug Fixes

* S2 pre-flight ([#21](https://github.com/bigknoxy/janus/issues/21)) ([5794615](https://github.com/bigknoxy/janus/commit/5794615360bbd8746c826c353a50a9d0e0ffd937))

## [0.6.0](https://github.com/bigknoxy/janus/compare/v0.5.1...v0.6.0) (2026-09-26)


### Features

* adversarial corpus tier ([#19](https://github.com/bigknoxy/janus/issues/19)) ([c71c516](https://github.com/bigknoxy/janus/commit/c71c51651063e40b2594357a1195e57f765acae2))

## [0.5.1](https://github.com/bigknoxy/janus/compare/v0.5.0...v0.5.1) (2026-09-26)


### Bug Fixes

* path anchors override margin ([#17](https://github.com/bigknoxy/janus/issues/17)) ([e065688](https://github.com/bigknoxy/janus/commit/e065688c4dc276e27fa8b17448f2daae83260f2b))

## [0.5.0](https://github.com/bigknoxy/janus/compare/v0.4.2...v0.5.0) (2026-09-26)


### Features

* literal anchors override margin hedges ([#15](https://github.com/bigknoxy/janus/issues/15)) ([d14f674](https://github.com/bigknoxy/janus/commit/d14f6748129f228445f6e62de33ec0b5e95c4894))

## [0.4.2](https://github.com/bigknoxy/janus/compare/v0.4.1...v0.4.2) (2026-09-26)


### Documentation

* calibration probe falsified ([#13](https://github.com/bigknoxy/janus/issues/13)) ([cfeec09](https://github.com/bigknoxy/janus/commit/cfeec093db9e2a0aeefc408d32bacaa73d1a9dd7))

## [0.4.1](https://github.com/bigknoxy/janus/compare/v0.4.0...v0.4.1) (2026-09-25)


### Bug Fixes

* anchor rule for vague prompts ([#11](https://github.com/bigknoxy/janus/issues/11)) ([97c2da9](https://github.com/bigknoxy/janus/commit/97c2da9f5b87896b1c322d0925dabaeb453c6dd7))

## [0.4.0](https://github.com/bigknoxy/janus/compare/v0.3.0...v0.4.0) (2026-09-25)


### Features

* dogfood check-in pushes to Telegram ([#8](https://github.com/bigknoxy/janus/issues/8)) ([de4b3c4](https://github.com/bigknoxy/janus/commit/de4b3c469059c5c1bb7799f1b40b60c6d92dae2b))


### Bug Fixes

* asymmetric gate floors ([#10](https://github.com/bigknoxy/janus/issues/10)) ([547a0f0](https://github.com/bigknoxy/janus/commit/547a0f0f048b1a0e1975cbc7c2b0545315ee7aaf))

## [0.3.0](https://github.com/bigknoxy/janus/compare/v0.2.0...v0.3.0) (2026-09-25)


### Features

* symbol targeting for large files ([#5](https://github.com/bigknoxy/janus/issues/5)) ([4863561](https://github.com/bigknoxy/janus/commit/48635615c026c9bc87ec3a411dce3bc9cc4ceb5e))

## [0.2.0](https://github.com/bigknoxy/janus/compare/v0.1.0...v0.2.0) (2026-09-25)


### Features

* tier-3 AST patch application + real-issue eval corpus ([#2](https://github.com/bigknoxy/janus/issues/2)) ([2a01903](https://github.com/bigknoxy/janus/commit/2a01903b86b6d61ec834f9beb5327a9c7581641e))

## 0.1.0 (2026-09-24)


### Features

* public release packaging — CI matrix, release-please, themed Pages site, one-line install/uninstall, docs (architecture/config/dev/security) ([58e715e](https://github.com/bigknoxy/janus/commit/58e715e91cf51022b71ae82896da7ebafd7c8c5c))


### Bug Fixes

* installer elif cleanup ([4ee07ab](https://github.com/bigknoxy/janus/commit/4ee07ab4106a5d8a84a8698b99d859ecf436368d))
