# Public Redactions

This public branch preserves the bundle structure but removes live authentication material.

Redacted before publication:
- all `hermes-home/auth.json` files under `snapshot/` and `restore-rollbacks/`
- test credentials in root handoff markdown files

The goal is to keep the audit trail and rollback structure without exposing reusable credentials.
