"""Explicit allowlist for the ordinary market-reference response."""


def public_reference(raw):
    def example(e):
        return {k:e[k] for k in ("amount","currency","observed_at") if k in e}

    guidance=raw.get("guidance",{})
    groups=[]
    for g in guidance.get("aleto_reference",[]):
        row={k:g[k] for k in ("currency","condition","match","offer_count","minimum","maximum","average","observed_at") if k in g}
        row["examples"]=[example(e) for e in g.get("examples",[])]
        groups.append(row)
    return dict(status=raw.get("status"),checked_at=raw.get("checked_at"),
        observed_at=raw.get("observed_at"),fresh_data_fetched=bool(raw.get("fresh_data_fetched")),
        truncated=bool(guidance.get("truncated")),references=groups,
        historical=[example(e) for e in raw.get("offers",[]) if e.get("status")=="historical_not_recommendation"])
