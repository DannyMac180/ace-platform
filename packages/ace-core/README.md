# ace-core

`ace-core` is the extracted shared OSS domain package for ACE.

It contains the local playbook engine and orchestration code that belongs on the
public side of the OSS/cloud boundary. The package is intentionally isolated
from `ace_platform` so it can be built and published independently of the
hosted control-plane code.

## Scope

- ACE orchestration (`ACE`, `Generator`, `Reflector`, `Curator`)
- Playbook manipulation helpers
- Local logging and LLM utility modules

## Non-scope

- Hosted auth, billing, metering, entitlements, or other cloud-only services
- `ace_platform` application code
- Finance benchmark datasets and scripts, which remain in the legacy upstream
  tree until later extraction work

## Build

```bash
source ../../venv/bin/activate && python -m build
```
