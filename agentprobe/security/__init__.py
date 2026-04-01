"""Security Scorer — 71 checks across 4 categories, 0-100 score.

Available in AgentProbe Pro. Learn more: https://agentprobe.dev/pro
"""


class SecurityScorer:
    """Score agent security — available in AgentProbe Pro."""

    def score(self, *args, **kwargs):
        raise NotImplementedError(
            "Security Scorer is available in AgentProbe Pro. "
            "Upgrade at https://agentprobe.dev/pro"
        )
