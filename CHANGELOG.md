# Changelog

All notable changes to this project will be documented in this file.

## [1.0.0] - 2026-05-29

### Added

- Initial open-source release of ShuyuanCore
- Apache 2.0 license, contributing guide, code of conduct, and security policy
- GitHub Actions CI (pytest, ruff, mypy)
- `shuyuancore` CLI entry point via `pip install -e .`

### Changed

- Repository URLs point to `https://github.com/Shuyuanverse/Shuyuancore`
- Copyright holder: 山野 (Shuyuanverse)
- README: clarify implemented vs planned platform integrations
- Removed runtime artifacts from version control; improved `.gitignore`

### Fixed

- Lint issues in persona modules for CI ruff checks
