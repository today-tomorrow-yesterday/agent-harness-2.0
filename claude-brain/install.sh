#!/bin/bash
# ============================================================================
# claude-brain installer — DEPRECATED in agent-harness
# ============================================================================
#
# This was the upstream (mikeadolan/claude-brain) one-line bootstrap. In
# agent-harness, claude-brain is set up as part of the harness onboarding, not
# as a standalone one-shot install.
#
# Use the guided onboarding instead: open the repo in Claude Code and say
# "onboard me" (or run /onboard). See ONBOARDING.md.
#
# Manual fallback:
#   python3 -m pip install -r claude-brain/requirements.txt
#   python3 claude-brain/scripts/brain-setup.py
# ============================================================================

echo "This installer is deprecated. See ONBOARDING.md (or run /onboard in Claude Code)."
echo "Manual: pip install -r claude-brain/requirements.txt && python3 claude-brain/scripts/brain-setup.py"
exit 1
