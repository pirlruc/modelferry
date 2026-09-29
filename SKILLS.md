<!-- Generated from .cursor/rules by scripts/render-agent-instructions.py. Edit the .mdc files, then re-run that script. -->

# Skills

Index of the file-scoped Cursor rules. Each row's instructions are in that `SKILL.md` ([Agent Skills](https://agentskills.io/specification)). Cursor applies the matching `.cursor/rules/*.mdc` glob and does not auto-invoke these skills. Other agents apply a skill when its description matches the files being edited.

| Skill | Globs | Instructions |
|-------|-------|--------------|
| `python-quality-gates` | `**/*.py` | [SKILL.md](.agents/skills/python-quality-gates/SKILL.md) |
| `container-images` | `**/Dockerfile*,**/.dockerignore,**/container-structure-test*.y*ml,**/*compose*.y*ml` | [SKILL.md](.agents/skills/container-images/SKILL.md) |
| `dependency-updates` | `**/dependabot.yml,**/dependabot.yaml` | [SKILL.md](.agents/skills/dependency-updates/SKILL.md) |
| `supply-chain-artifacts` | `**/*sbom*,**/cosign*,**/*provenance*,**/license_gate*,**/attestation*` | [SKILL.md](.agents/skills/supply-chain-artifacts/SKILL.md) |
| `release-publish` | `**/CHANGELOG*,**/RELEASE*,**/.release-please*,**/release-please*,**/commitizen*,**/cz.yaml,**/.cz.toml,**/action-gh-release*` | [SKILL.md](.agents/skills/release-publish/SKILL.md) |
