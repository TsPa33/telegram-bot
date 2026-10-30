"""Bounded SQL projection of the immutable stock-sale ledger, never current prices."""
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo
from sqlalchemy import text

# Lateral lookup is used ONLY for historical operations without sale metadata.
# One snapshot per operation prevents multiplying sales through joins/events.
AGGREGATE = text('''
WITH scoped AS (
 SELECT id, account_id, created_at, before::jsonb AS b, after::jsonb AS a
 FROM operations
 WHERE account_id=:account_id AND type='sale' AND (CAST(:manager_id AS varchar) IS NULL OR actor_id=:manager_id)
   AND created_at>=:start AND created_at<:end
), projected AS (
 SELECT o.id, date_trunc(:interval, o.created_at AT TIME ZONE :tz)::date AS bucket,
 CASE WHEN o.b->>'quantity' ~ '^[0-9]{1,10}$' AND o.a->>'quantity' ~ '^[0-9]{1,10}$'
      THEN (o.b->>'quantity')::bigint-(o.a->>'quantity')::bigint ELSE 0 END AS units,
 CASE WHEN jsonb_typeof(o.a->'sale')='object' AND o.a->'sale'<>'{}'::jsonb
      THEN o.a->'sale' ELSE legacy.financial END AS financial
 FROM scoped o
 LEFT JOIN LATERAL (
   SELECT jsonb_build_object('unit_price', item->>'unit_price',
          'total',item->>'line_total','currency',item->>'currency') AS financial
   FROM order_lines l
   JOIN order_events e ON e.order_id=l.order_id AND e.account_id=o.account_id
        AND e.type='sale_confirmed'
   CROSS JOIN LATERAL jsonb_array_elements(
       CASE WHEN jsonb_typeof(e.data::jsonb->'lines')='array'
            THEN e.data::jsonb->'lines' ELSE '[]'::jsonb END) AS item
   WHERE l.account_id=o.account_id AND l.sale_operation_id=o.id
     AND item->>'sale_operation_id'=o.id
   ORDER BY e.created_at,e.id LIMIT 1
 ) legacy ON o.a->'sale' IS NULL OR o.a->'sale' IN ('null'::jsonb,'{}'::jsonb)
), checked AS (
 SELECT *,
 CASE WHEN financial->>'unit_price' ~ '^[0-9]{1,14}(\\.[0-9]{1,2})?$'
      THEN (financial->>'unit_price')::numeric END AS price,
 CASE WHEN financial->>'total' ~ '^[0-9]{1,20}(\\.[0-9]{1,2})?$'
      THEN (financial->>'total')::numeric END AS amount
 FROM projected WHERE units>0
), valued AS (
 SELECT *, CASE WHEN financial->>'currency' IN ('UAH','USD')
   AND price IS NOT NULL AND amount=price*units
   THEN financial->>'currency' END AS currency
 FROM checked
)
SELECT bucket,currency,sum(units) AS units,count(*) AS sales_count,
       CASE WHEN currency IS NOT NULL THEN sum(amount) END AS amount
FROM valued GROUP BY bucket,currency ORDER BY bucket,currency NULLS LAST
''')


def bucket_start(day: date, interval: str) -> date:
    if interval == 'month': return day.replace(day=1)
    if interval == 'week': return day - timedelta(days=day.weekday())
    return day


def next_bucket(day: date, interval: str) -> date:
    if interval == 'month':
        return (day.replace(day=28)+timedelta(days=4)).replace(day=1)
    return day+timedelta(days=7 if interval == 'week' else 1)


def summary(db, account_id, date_from, date_to, interval, tz, *, manager_id=None):
    zone=ZoneInfo(tz)
    start=datetime.combine(date_from,time.min,zone).astimezone(timezone.utc)
    end=datetime.combine(date_to+timedelta(days=1),time.min,zone).astimezone(timezone.utc)
    # Bound expensive historical projections. Transaction-local, never global config.
    db.execute(text("SELECT set_config('statement_timeout','5000',true)"))
    rows=db.execute(AGGREGATE,{'account_id':account_id,'start':start,'end':end,'interval':interval,'tz':tz,'manager_id':manager_id}).mappings().all()
    periods={}
    day=bucket_start(date_from,interval)
    while day<=date_to:
        periods[day]={'date':day.isoformat(),'units':0,'sales_count':0,'unpriced_units':0,'unpriced_sales':0,'by_currency':[]}
        day=next_bucket(day,interval)
    totals={}
    for row in rows:
        period=periods[row['bucket']]
        units=int(row['units']);count=int(row['sales_count'])
        period['units']+=units;period['sales_count']+=count
        if row['currency'] is None:
            period['unpriced_units']+=units;period['unpriced_sales']+=count
        else:
            currency=row['currency'];amount=row['amount']
            period['by_currency'].append({'currency':currency,'amount':format(amount,'.2f'),'units':units,'sales_count':count})
            total=totals.setdefault(currency,{'currency':currency,'amount':Decimal(0),'units':0,'sales_count':0})
            total['amount']+=amount;total['units']+=units;total['sales_count']+=count
    return {'date_from':date_from.isoformat(),'date_to':date_to.isoformat(),'interval':interval,'timezone':tz,
            'date_semantics':'operation_created_at','returns_supported':False,'periods':list(periods.values()),
            'totals_by_currency':[{**v,'amount':format(v['amount'],'.2f')} for _,v in sorted(totals.items())],
            'units':sum(p['units'] for p in periods.values()),
            'sales_count':sum(p['sales_count'] for p in periods.values()),
            'unpriced_units':sum(p['unpriced_units'] for p in periods.values())}
