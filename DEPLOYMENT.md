# Deployment Checklist

## Pre-Release Checklist

### Code Quality
- [x] Package structure created
- [x] All imports refactored to absolute
- [x] Unified CLI implemented
- [x] Schema bundled as package data
- [x] Entry point configured correctly
- [ ] All commands tested end-to-end
- [ ] Unit tests added (optional for MVP)

### Documentation
- [x] README.md updated
- [x] SKILL.md created
- [x] REFERENCE.md created
- [x] INSTALL.md created
- [x] REFACTOR_SUMMARY.md created
- [ ] LICENSE file added
- [ ] CHANGELOG.md created (optional)

### Configuration
- [x] pyproject.toml updated with correct metadata
- [ ] Author name/email updated in pyproject.toml
- [ ] GitHub URLs updated in pyproject.toml
- [ ] Version number confirmed (currently 0.2.0)

### Testing
- [x] `uv tool install -e .` works
- [x] `claude-finder --help` shows all commands
- [x] `claude-finder init` creates database
- [x] `claude-finder list` works
- [ ] `claude-finder search` tested with fresh DB
- [ ] `claude-finder context` tested
- [ ] `claude-finder tree` tested
- [ ] `claude-finder watch` tested
- [ ] Skill activation tested in Claude Code

## Release Process

### 1. Prepare Repository
```bash
# Update author info
edit pyproject.toml  # Change "Your Name" and email

# Add LICENSE
cat > LICENSE << 'EOF'
MIT License

Copyright (c) 2025 [Your Name]

[Full MIT license text]
EOF

# Update URLs
edit pyproject.toml  # Update GitHub URLs
```

### 2. Version and Tag
```bash
# Ensure version is correct in pyproject.toml
grep version pyproject.toml

# Commit final changes
git add .
git commit -m "Release v0.2.0: Complete refactor with Skill"

# Tag release
git tag -a v0.2.0 -m "Version 0.2.0 - Package refactor with Claude Code Skill"
```

### 3. Build Package
```bash
# Install build tools
pip install build twine

# Build
python -m build

# Check dist/
ls -lh dist/
# Should see:
#   claude_finder-0.2.0-py3-none-any.whl
#   claude_finder-0.2.0.tar.gz
```

### 4. Test Package Locally
```bash
# Uninstall dev version
uv tool uninstall claude-finder

# Install from wheel
uv tool install dist/claude_finder-0.2.0-py3-none-any.whl

# Test
claude-finder --help
claude-finder init --days 1 --no-summarize
claude-finder list
```

### 5. Push to GitHub
```bash
# Push code
git push origin main

# Push tags
git push origin v0.2.0

# Create GitHub release
gh release create v0.2.0 \
  --title "v0.2.0 - Package Refactor" \
  --notes-file REFACTOR_SUMMARY.md \
  dist/*
```

### 6. Publish to PyPI
```bash
# Check package
twine check dist/*

# Upload to Test PyPI (optional)
twine upload --repository testpypi dist/*

# Test install from Test PyPI
pip install --index-url https://test.pypi.org/simple/ claude-finder

# Upload to PyPI (production)
twine upload dist/*

# Verify
pip search claude-finder  # or check https://pypi.org/project/claude-finder/
```

### 7. Verify Installation
```bash
# Clean install test
docker run -it python:3.12 bash
pip install claude-finder
claude-finder --help
```

## Post-Release

### Announce
- [ ] Update project README with PyPI badge
- [ ] Tweet/post about release (optional)
- [ ] Add to Claude Code plugins list (if applicable)

### Monitor
- [ ] Check PyPI download stats
- [ ] Monitor GitHub issues
- [ ] Collect user feedback

### Skill Distribution
- [ ] Create separate skill-only repo (optional)
- [ ] Add to Claude Code Skill marketplace (when available)
- [ ] Share installation instructions

## Quick Deploy (MVP)

For immediate testing without full release:

```bash
# 1. Update author
edit pyproject.toml

# 2. Commit
git commit -am "Update package metadata"

# 3. Install locally
uv tool install -e . --force

# 4. Install Skill
mkdir -p ~/.claude/skills/conversation-search
cp skill/* ~/.claude/skills/conversation-search/

# 5. Test
claude-finder init --days 7 --no-summarize
# Ask Claude: "What did we discuss about X?"
```

## Rollback Plan

If issues are discovered:

```bash
# Yank bad release from PyPI
twine upload --repository pypi --skip-existing dist/*

# Or mark as yanked on PyPI web interface

# Push hotfix
git checkout -b hotfix/v0.2.1
# Make fixes
git commit -am "Hotfix for X"
git tag v0.2.1
python -m build
twine upload dist/*
```

## Support

After release, users may encounter:

### Common Issues
1. **Import errors** → Ensure Python 3.9+
2. **Database errors** → Run `claude-finder init --force`
3. **Skill not found** → Check `~/.claude/skills/conversation-search/`
4. **Command not found** → Check PATH includes uv bin dir

### Where to Get Help
- GitHub Issues: `https://github.com/yourusername/claude-finder/issues`
- Documentation: See README.md, skill/REFERENCE.md
- Quick fix: `uv tool uninstall claude-finder && uv tool install claude-finder`

## Metrics to Track

- [ ] PyPI downloads per week
- [ ] GitHub stars/forks
- [ ] Issue open/close rate
- [ ] User feedback sentiment
- [ ] Skill activation success rate (if measurable)

## Future Releases

### v0.3.0 Ideas
- Fix FTS index sync bug
- Add vector embeddings for semantic search
- Web UI for conversation visualization
- Export conversations as markdown
- Improved performance metrics

### v1.0.0 Criteria
- All core commands working flawlessly
- Comprehensive test coverage
- Documentation complete
- Active user base (10+ stars)
- Skill proven to work well with Claude
