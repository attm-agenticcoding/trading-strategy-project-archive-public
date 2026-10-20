"""Extracted portfolio capital-gain/loss-carryforward arithmetic.

This is an isolated research assumption, not a jurisdiction-specific tax model.
No private positions, trades or account data are included.
"""

def settle_gain(gain,loss_bank,rate,carry_losses):
    """Losses offset future portfolio capital gains; no outside tax refunds."""
    if gain<0:
        return 0.,loss_bank-gain if carry_losses else loss_bank,0.
    used=min(gain,loss_bank) if carry_losses else 0.
    tax=(gain-used)*rate
    return tax,loss_bank-used,used
