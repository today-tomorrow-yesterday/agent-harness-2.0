"""The Execution Layer: the gated "hands" of the harness.

Every real-world action flows score -> policy-gate -> durable-approval -> confined
run -> redacted log, on top of the Safety Harness (bin/runner). v1 enables exactly
one action class: read_external (read-only external fetch). Everything that mutates
the outside world ships built-but-gated.
"""
