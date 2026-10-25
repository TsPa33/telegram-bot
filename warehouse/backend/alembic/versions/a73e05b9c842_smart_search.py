"""Indexed read-only Smart Search; no inventory data backfill or shadow table."""
from alembic import op
revision='a73e05b9c842'
down_revision='d86f21a90b34'
branch_labels=None
depends_on=None

# Frozen transliteration; do not import a future mutable runtime normalizer.
MAP=dict(zip('абвгґдеёжзиіїйклмнопрстуфхцчшщъыьэюя',
 ['a','b','v','g','g','d','e','yo','zh','z','y','i','yi','i','k','l','m','n','o','p','r','s','t','u','f','kh','ts','ch','sh','shch','','y','','e','yu','ya']))
MAP['є']='ye'

def upgrade():
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')
    expr="lower(normalize(coalesce(value,''), NFKC))"
    expr=f"regexp_replace({expr}, '(\\d)[.,](\\d)', '\\1d\\2', 'g')"
    for char in "'’ʼ`":expr=f"replace({expr},'{char.replace(chr(39),chr(39)*2)}','')"
    for src,dst in MAP.items():expr=f"replace({expr},'{src}','{dst}')"
    expr=f"regexp_replace(normalize({expr}, NFKD), '[\u0300-\u036f]', '', 'g')"
    op.execute(f"""CREATE FUNCTION warehouse_search_text(value text) RETURNS text
        LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
        BEGIN RETURN trim(regexp_replace({expr}, '[^a-z0-9]+', ' ', 'g')); END $$""")
    op.execute("""CREATE FUNCTION warehouse_search_code(value text) RETURNS text
        LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
        SELECT regexp_replace(lower(normalize(coalesce(value,''), NFKC)), '[^[:alnum:]]', '', 'g') $$""")
    op.execute("CREATE INDEX ix_parts_smart_fts ON parts USING gin (to_tsvector('simple', warehouse_search_text(name))) WHERE NOT archived")
    op.execute("CREATE INDEX ix_parts_smart_trgm ON parts USING gin (warehouse_search_text(name) gin_trgm_ops) WHERE NOT archived")
    for field in ('oem_number','article_number'):
        op.execute(f"CREATE INDEX ix_parts_smart_{field} ON parts (account_id, warehouse_search_code({field})) WHERE NOT archived AND {field} <> ''")
    op.execute("CREATE INDEX ix_vehicle_smart_model ON vehicles USING gin (to_tsvector('simple', warehouse_search_text(model)))")
    op.execute("CREATE INDEX ix_vehicle_smart_brand ON vehicles (account_id,warehouse_search_text(manufacturer))")

def downgrade():
    for name in ('ix_vehicle_smart_brand','ix_vehicle_smart_model','ix_parts_smart_article_number','ix_parts_smart_oem_number','ix_parts_smart_trgm','ix_parts_smart_fts'):
        op.execute(f'DROP INDEX {name}')
    op.execute('DROP FUNCTION warehouse_search_code(text)')
    op.execute('DROP FUNCTION warehouse_search_text(text)')
    # pg_trgm may predate Warehouse or be used by other code. Never drop it.
