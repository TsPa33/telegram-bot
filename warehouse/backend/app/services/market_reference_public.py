"""Explicit allowlist for the ordinary market-reference response."""


def public_example(e):
    return {k:e[k] for k in ("amount","currency","observed_at") if k in e}


def public_groups(groups):
    result=[]
    for g in groups:
        row={k:g[k] for k in ("currency","condition","match","offer_count","minimum","maximum","average","observed_at","availability","assembly") if k in g}
        row["examples"]=[public_example(e) for e in g.get("examples",[])]
        result.append(row)
    return result


def public_reference(raw):
    guidance=raw.get("guidance",{})
    return dict(status=raw.get("status"),checked_at=raw.get("checked_at"),
        observed_at=raw.get("observed_at"),fresh_data_fetched=bool(raw.get("fresh_data_fetched")),
        truncated=bool(guidance.get("truncated")),references=public_groups(guidance.get("aleto_reference",[])),
        historical=[public_example(e) for e in raw.get("offers",[]) if e.get("status")=="historical_not_recommendation"])
