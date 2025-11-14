# Version Management

## Current Version: 0.4.3

## Version Locations (Keep in Sync)

When bumping the version, update ALL of these files:

1. **pyproject.toml** - Line 3: `version = "0.4.3"`
2. **src/conversation_search/cli.py** - Line 12: `__version__ = "0.4.3"`
3. **.claude-plugin/plugin.json** - Line 3: `"version": "0.4.3"`
4. **.claude-plugin/marketplace.json** - Line 12: `"version": "0.4.3"`

## Quick Sync Command

```bash
# Find all version strings (should all show same version)
grep -n "version.*0\." pyproject.toml .claude-plugin/*.json src/conversation_search/cli.py
```

## Version Strategy (MVP)

- **Minimum supported version**: 0.4.0 (documented in SKILL.md)
- **Auto-upgrade on skill activation**: SKILL.md instructs Claude to run `uv tool upgrade cc-conversation-search`
- **Manual sync**: Update all 4 files when bumping version (no automation yet)
- **Future**: Consider build script to auto-sync from pyproject.toml

## How It Works

When users update the plugin via `/plugin update conversation-search`:
1. Plugin files get updated (including new SKILL.md)
2. SKILL.md tells Claude to run `uv tool upgrade cc-conversation-search` on activation
3. User gets latest CLI automatically
4. No version mismatch issues

## Breaking Changes

Only bump minor version (0.4 → 0.5) for breaking changes. Update SKILL.md minimum version if needed.
