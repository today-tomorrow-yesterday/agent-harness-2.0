"""Action implementations. An Action is anything the Execution Layer can run:

    name: str            # short identifier for logs
    action_class: str    # 'read_external' | 'write_workspace' | 'run_script' | ...
    blast_radius: str    # 'none' | 'workspace' | 'external_write' | 'unrestricted'
    self_risk: str       # the action's own LOW/MED/HIGH hint (can only be raised)
    def summary(self) -> str: ...   # human-readable, fed to the risk scorer
    def run(self) -> Any: ...       # do the work; raises on failure / egress-deny

v1 ships one: actions.read_web.ReadWeb.
"""
