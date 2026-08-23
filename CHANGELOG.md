# Changelog

All notable changes made on the `nisedo-dev` branch relative to `main` are
recorded here.

## Unreleased — `nisedo-dev`

### Added

- Generate a project-level index for local Solidity scans, linking every
  deployable root-contract dashboard. The CLI prints the index URL before the
  individual dashboard URLs, and the behavior is covered by tests and
  documentation. ([5fd6050](https://github.com/nisedo/onboardme/commit/5fd6050))
- Add a `Home` link to local contract dashboards that returns to the correct
  project index. ([8fa4206](https://github.com/nisedo/onboardme/commit/8fa4206))

### Changed

- Raise the initial source-code font default from 10px to 14px, with a 20px
  line height. This was later superseded by the 18px default below.
  ([4061d99](https://github.com/nisedo/onboardme/commit/4061d99))
- Replace synthetic `0x…` function-card titles with the useful
  `Contract.sol function()` identity. ([38e8d1e](https://github.com/nisedo/onboardme/commit/38e8d1e))
- Correct function identities to remain beside their icons while being
  centered vertically within the header. ([aecb2bc](https://github.com/nisedo/onboardme/commit/aecb2bc))
- Increase function-identity text from 16px to 20px.
  ([f7fb317](https://github.com/nisedo/onboardme/commit/f7fb317))
- Increase source-code text to an effective 18px with a 25px line height, and
  version the persisted font preference so the new default takes effect.
  ([b31d552](https://github.com/nisedo/onboardme/commit/b31d552))
- Tune the source-code font down to 16px with a 22px line height after live UI
  review showed that 18px was too large.

### Removed

- Remove the segmented cyan ornament from the top edge of dashboard cards.
  ([690723d](https://github.com/nisedo/onboardme/commit/690723d))
- Remove the “May the bugs be with you <3” sidebar-footer tagline.
  ([0d8ae4e](https://github.com/nisedo/onboardme/commit/0d8ae4e))
- Remove the purely decorative three-dot sidebar footer and reclaim its empty
  space. ([8b90261](https://github.com/nisedo/onboardme/commit/8b90261))

### Fixed

- Treat a missing saved code-font preference as absent instead of converting
  it to zero and clamping fresh dashboards to the 8px minimum.
  ([b31d552](https://github.com/nisedo/onboardme/commit/b31d552))
