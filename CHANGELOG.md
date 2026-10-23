# Changelog

## [0.5.1](https://github.com/sj-tech-sweden/stagewire/compare/stagewire-v0.5.0...stagewire-v0.5.1) (2026-10-23)


### Bug Fixes

* **web:** move channel-list sidebar behind a dropdown on mobile ([af94b26](https://github.com/sj-tech-sweden/stagewire/commit/af94b26a5830021864284646cec0db526cac8c78))
* **web:** move channel-list sidebar behind a dropdown on mobile ([afe34da](https://github.com/sj-tech-sweden/stagewire/commit/afe34dad0fffb2b4dd3deadbd884600e9ca26fa2))

## [0.5.0](https://github.com/sj-tech-sweden/stagewire/compare/stagewire-v0.4.0...stagewire-v0.5.0) (2026-10-23)


### Features

* **web:** add favicon.io favicon pack and web manifest ([0b7bb70](https://github.com/sj-tech-sweden/stagewire/commit/0b7bb70f41d549bf85ab5dad7052c44484a523f7))
* **web:** add favicon.io favicon pack and web manifest ([dc28196](https://github.com/sj-tech-sweden/stagewire/commit/dc281964899a65fdb629b1df7c7af593ce9f6f6e))
* **web:** make table-heavy pages mobile-friendly with cards ([4bcb744](https://github.com/sj-tech-sweden/stagewire/commit/4bcb744dfb47a94fc5d889baf0d45006cb7cda96))
* **web:** mobile-friendly cards for table-heavy pages ([b950e69](https://github.com/sj-tech-sweden/stagewire/commit/b950e6943bc361d8bc65f05027341a901d53b516))


### Bug Fixes

* **deps:** update frontend dependencies ([8fea682](https://github.com/sj-tech-sweden/stagewire/commit/8fea682a0d2e4c5b54f7b4adc9200e5d925ad9cd))
* **deps:** update frontend dependencies (major) ([ed97ec3](https://github.com/sj-tech-sweden/stagewire/commit/ed97ec31f2647bc5f706b0892477afde7ffbabae))
* **web:** bind quasar dev server with -H instead of unsupported --host ([a2d9e67](https://github.com/sj-tech-sweden/stagewire/commit/a2d9e671802cc30539b2fb7fbde5f2e4fe7879f0))
* **web:** inject env via import.meta.env after app-vite v3 upgrade ([2e1fd5c](https://github.com/sj-tech-sweden/stagewire/commit/2e1fd5cf8d4068471c0a39211ebcec60166bcb6f))
* **web:** migrate ESLint to flat config (eslint.config.js) for ESLint 10 ([2c3d736](https://github.com/sj-tech-sweden/stagewire/commit/2c3d7368cddd9e82a2659d83914fa28ad425eaaa))
* **web:** migrate ESLint to flat config for ESLint 10 ([1c65f4b](https://github.com/sj-tech-sweden/stagewire/commit/1c65f4b3ae719abaf9344249112549adace9ec68))

## [0.4.0](https://github.com/sj-tech-sweden/stagewire/compare/stagewire-v0.3.0...stagewire-v0.4.0) (2026-10-23)


### Features

* add console channel-list export plugins (CSV/XLSX + Allen & Heath QU/CQ/GLD) ([eb882b7](https://github.com/sj-tech-sweden/stagewire/commit/eb882b7c20c6a1c2055f4470503a3a2507a58759))
* console channel-list export plugins (CSV/XLSX + Allen & Heath QU/CQ/GLD) ([f4018ce](https://github.com/sj-tech-sweden/stagewire/commit/f4018ce8d6c60facc2c6f31be5f7967af4e591f2))


### Bug Fixes

* **deps:** update dependency @quasar/extras to v2 ([1921b59](https://github.com/sj-tech-sweden/stagewire/commit/1921b594e52b3bc50dd0dcde16b96584274905d3))
* **deps:** update dependency @quasar/extras to v2 ([bd174a3](https://github.com/sj-tech-sweden/stagewire/commit/bd174a35063b8f896ba501c72bc77208e16889dc))
* **deps:** update dependency konva to v10 ([d194f75](https://github.com/sj-tech-sweden/stagewire/commit/d194f75a49948f4741f84048a831d4cb50ebc170))
* **deps:** update dependency konva to v10 ([974e6c7](https://github.com/sj-tech-sweden/stagewire/commit/974e6c756947809600a5d44242c20a3d667e9101))
* **deps:** update dependency marked to v18 ([eb26d32](https://github.com/sj-tech-sweden/stagewire/commit/eb26d32fcedd4470ccaf2df45a1488e8afaeed96))
* **deps:** update dependency marked to v18 ([63b512c](https://github.com/sj-tech-sweden/stagewire/commit/63b512c97c928f2104ea842f182cc41b573638e4))
* normalize DATABASE_URL to psycopg3 so cnpg migrations succeed ([accff89](https://github.com/sj-tech-sweden/stagewire/commit/accff892af22afb1beb1e44df9db95d6d94db3da))
* normalize DATABASE_URL to psycopg3 so cnpg migrations succeed ([510709c](https://github.com/sj-tech-sweden/stagewire/commit/510709ca2522d26c815aede78b9bcde44c653b2b))

## [0.3.0](https://github.com/sj-tech-sweden/stagewire/compare/stagewire-v0.2.0...stagewire-v0.3.0) (2026-10-22)


### Features

* implement Stagewire stage-plot, patch lists, and stockwire-rental integration ([62b3efd](https://github.com/sj-tech-sweden/stagewire/commit/62b3efd95bc446b3c40d200abb186d0ebb27642d))


### Bug Fixes

* **e2e:** make login helper wait for authenticated UI, not URL ([7c07679](https://github.com/sj-tech-sweden/stagewire/commit/7c0767934fb815e0200a0920a8ed7e1e39b2adae))
* **web:** align channels e2e spec with dialog-based UI ([092957c](https://github.com/sj-tech-sweden/stagewire/commit/092957cf4808523ddd50cd32c3dab1459a3db6af))
* **web:** resolve API base URL at runtime from Pod env ([e6ee388](https://github.com/sj-tech-sweden/stagewire/commit/e6ee388a094ad54f75512d44d1fe59768c2455a4))
* **web:** silence v-html XSS lint warning on MarkdownText ([deb8c43](https://github.com/sj-tech-sweden/stagewire/commit/deb8c43464ad113d8251ccfeddc9fe3b73085b4b))
