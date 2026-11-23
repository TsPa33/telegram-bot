"""Versioned source bindings in the existing, vehicle-locked catalogue state."""

from dataclasses import asdict, dataclass

KEY = 'catalogue_item_bindings'


@dataclass(frozen=True)
class PlanItemBinding:
    source_modification_id: int
    product_id: int
    snapshot_sha: str
    manufacturer_id: int
    article_count: int

    @classmethod
    def from_product(cls, payload, product):
        return cls(payload['car_id'], product['product_id'], payload['source_snapshot_sha'],
                   payload['manufacturer_id'], product['article_count'])


def active_binding(vehicle, row_id):
    history = (vehicle.dismantling_v3 or {}).get(KEY, {}).get(row_id)
    return history[-1] if history else None


def update_bindings(vehicle, existing_rows, rows_by_product, previous, payload):
    state = vehicle.dismantling_v3 or {}
    bindings = dict(state.get(KEY, {}))
    if previous:
        old_products = {p['product_id']: p for p in previous['categories']}
        for row in existing_rows:
            history = bindings.get(row.id)
            if history:
                if history[-1] is None:
                    continue
                binding = dict(history[-1])
            else:
                product_key = row.catalog_key.rsplit(':', 1)[-1]
                product = old_products.get(int(product_key)) if product_key.isdigit() else None
                if not product or row.catalog_key != f"car:{previous['car_id']}:product:{product['product_id']}":
                    continue
                binding = asdict(PlanItemBinding.from_product(previous, product))
            ref = state.get('volvo_oem_references', {}).get(row.id)
            if ref and (ref.get('source_modification_id'), ref.get('product_id'), ref.get('snapshot_sha')) == (
                binding['source_modification_id'], binding['product_id'], binding['snapshot_sha']
            ):
                binding['oem_evidence'] = ref
            bindings[row.id] = [*(history or [])[:-1], binding]

    active = {
        rows_by_product[p['product_id']].id: asdict(PlanItemBinding.from_product(payload, p))
        for p in payload['categories'] if p['product_id'] in rows_by_product
    }
    for row_id in bindings.keys() | active.keys():
        history = bindings.get(row_id, [])
        target = active.get(row_id)
        current = history[-1] if history else None
        same_binding = current is target or (
            current is not None and target is not None
            and all(current.get(key) == value for key, value in target.items())
        )
        if not same_binding:
            bindings[row_id] = [*history, target]
    return bindings


def record_evidence(bindings, row_id, offers, reference):
    history = bindings.get(row_id)
    if not history or history[-1] is None:
        return False
    binding = history[-1]
    keys = {(offer['supplier_id'], offer['article_nr']) for offer in offers}
    if len(keys) != binding['article_count']:
        return False
    current = {**binding, 'supplier_articles': [
        dict(supplier_id=supplier_id, article_number=number) for supplier_id, number in sorted(keys)
    ]}
    if reference:
        current['oem_evidence'] = reference
    if current == binding:
        return False
    bindings[row_id] = [*history[:-1], current]
    return True
