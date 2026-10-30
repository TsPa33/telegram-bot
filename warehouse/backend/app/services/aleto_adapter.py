"""Bounded, network-free Aleto listing adapter. Only synthetic packaged fixtures enabled.

Selectors/category keys adapted from supplied Aleto Parser MVP; HTTP, SQLite and
per-page deduplication deliberately excluded. No automatic source approval.
"""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlsplit, unquote
from app.services.catalogue_format import ImportRow

VERSION = 'r83-synthetic-v1'
ROOTS = {
 'XC40':'https://aleto.ua/car/volvo-xc40-2019-2023/',
 'XC60':'https://aleto.ua/ua/car/volvo-xc60-2018-2023/',
 'XC90':'https://aleto.ua/ua/car/volvo-xc90-16-/',
}
MAX_PAGE_BYTES=262144
MAX_ARTIFACT_BYTES=1048576
MAX_PAGES=8
MAX_RECORDS=500
DIRECTORY=Path(__file__).with_name('aleto_fixtures')


def encoded(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()


def sha(raw):return hashlib.sha256(raw).hexdigest()


def clean(value):return re.sub(r'\s+',' ',value or '').strip()


def source_url(value,base=None):
    """Validate identifiers only: this function never connects to the URL."""
    if not isinstance(value,str) or not value or len(value)>2000 or any(ord(c)<33 for c in value) or '\\' in value:raise ValueError('INVALID_SOURCE_URL')
    url=urljoin(base,value) if base else value
    parsed=urlsplit(url)
    if parsed.scheme!='https' or parsed.hostname not in ('aleto.ua','www.aleto.ua') or parsed.username or parsed.password or parsed.port not in (None,443) or parsed.fragment:raise ValueError('INVALID_SOURCE_URL')
    path=unquote(parsed.path).lower()
    if any(x in ('.','..') for x in path.split('/')) or any(x in path.split('/') for x in ('personal','register','cart','search','search-adv')):raise ValueError('INVALID_SOURCE_URL')
    return url


@dataclass
class Node:
    tag:str
    attrs:dict=field(default_factory=dict)
    children:list=field(default_factory=list)
    def text(self):return clean(' '.join(n.text() if isinstance(n,Node) else n for n in self.children))
    def all(self):
        for n in self.children:
            if isinstance(n,Node):yield n;yield from n.all()
    def has(self,cls):return cls in self.attrs.get('class','').split()
    def find(self,*,cls=None,tag=None,attr=None):
        return next((n for n in self.all() if (not cls or n.has(cls)) and (not tag or n.tag==tag) and (not attr or attr in n.attrs)),None)


class Tree(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.root=Node('root');self.stack=[self.root];self.nodes=0
    def handle_starttag(self,tag,attrs):
        self.nodes+=1
        if self.nodes>10000 or len(self.stack)>64:raise ValueError('HTML_COMPLEXITY_LIMIT')
        node=Node(tag,dict(attrs));self.stack[-1].children.append(node)
        if tag not in ('area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'):self.stack.append(node)
    def handle_endtag(self,tag):
        for i in range(len(self.stack)-1,0,-1):
            if self.stack[i].tag==tag:del self.stack[i:];break
    def handle_data(self,data):self.stack[-1].children.append(data)


def price(value,currency):
    if not value:return None
    suffix={'uah':r'(?:грн\.?|₴|UAH)','usd':r'(?:\$|USD)'}[currency]
    # Full match: never silently strip signs, currencies or malformed punctuation.
    m=re.fullmatch(r'(\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)\s*'+suffix,clean(value),re.I)
    if not m:raise ValueError('INVALID_PRICE')
    try:amount=Decimal(re.sub(r'[ \u00a0\u202f]','',m[1]).replace(',','.'))
    except InvalidOperation:raise ValueError('INVALID_PRICE') from None
    if not amount.is_finite() or amount<=0 or amount>Decimal('9999999999.99'):raise ValueError('INVALID_PRICE')
    return str(amount.quantize(Decimal('.01')))


def parse_page(html,url,observed_at,model):
    source_url(url)
    if len(html.encode())>MAX_PAGE_BYTES:raise ValueError('PAGE_TOO_LARGE')
    stamp=datetime.fromisoformat(observed_at.replace('Z','+00:00'))
    if stamp.tzinfo is None:raise ValueError('MISSING_OBSERVATION_TIMEZONE')
    if model not in ROOTS:raise ValueError('UNSUPPORTED_MODEL')
    tree=Tree();tree.feed(html);tree.close()
    cards=[n for n in tree.root.all() if n.has('detail-item')]
    if len(cards)>MAX_RECORDS:raise ValueError('TOO_MANY_CARDS')
    records=[];issues=[];rows=[]
    for index,card in enumerate(cards,1):
        try:
            title_area=card.find(cls='detail-item-title');a=title_area.find(tag='a',attr='href') if title_area else None
            if not title_area or not a:raise ValueError('MISSING_TITLE_OR_URL')
            title=title_area.text();article=oem=''
            chars=card.find(cls='detail-item-chars')
            for n in chars.all() if chars else []:
                if n.tag!='small':continue
                b=n.find(tag='b')
                if not b:continue
                label=n.text().lower();value=b.text()
                if 'арт' in label:
                    if article and article!=value:raise ValueError('AMBIGUOUS_ARTICLE')
                    article=value
                elif 'ориг' in label or 'oem' in label:
                    if oem and oem!=value:raise ValueError('AMBIGUOUS_OEM')
                    oem=value
            if not article or not title:raise ValueError('MISSING_ARTICLE_OR_TITLE')
            p_uah=card.find(cls='detail-item-uprice');p_usd=card.find(cls='detail-item-price')
            category=subcategory=''
            script=card.find(tag='script')
            if script:
                for key,target in [('item_category2','category'),('item_category3','subcategory')]:
                    m=re.search(r'\b'+key+r'\s*:\s*([\'\"])(.*?)\1',script.text())
                    if m:
                        if target=='category':category=clean(m[2])
                        else:subcategory=clean(m[2])
            labels=card.find(cls='detail-item-labels')
            record=dict(article=article,oem=oem,title=title,price_uah=price(p_uah.text(),'uah') if p_uah else None,price_usd=price(p_usd.text(),'usd') if p_usd else None,url=source_url(a.attrs['href'],url),source_page=url,condition=labels.text() if labels else '',category=category,subcategory=subcategory,model='Volvo '+model,checked_at=observed_at,raw_excerpt=card.text()[:700],data_origin='synthetic_offline_fixture',adapter_version=VERSION)
            records.append(record)
            if not category or not subcategory:raise ValueError('MISSING_TAXONOMY')
            row=ImportRow.model_validate(dict(source='aleto-offline-fixture',source_article=article,manufacturer='Volvo',model=model,category=category,subcategory=subcategory,part_name=title,oem=oem,condition=record['condition'],price_uah=record['price_uah'],price_usd=record['price_usd'],source_url=record['url'],observed_at=observed_at,source_record={k:'' if v is None else str(v) for k,v in record.items()})).model_dump(mode='json')
            rows.append(row)
        except (ValueError,TypeError) as exc:
            code=str(exc) if re.fullmatch('[A-Z_]+',str(exc)) else 'INVALID_RECORD'
            issues.append(dict(card=index,code=code))
    links=[]
    for a in tree.root.all():
        if a.tag!='a' or 'href' not in a.attrs:continue
        href=a.attrs['href'];rel=a.attrs.get('rel','')
        if a.has('detail-cat-item') or 'next' in rel.split() or re.search(r'(?:page-\d+|[?&](?:page|PAGEN_\d+)=\d+|/page/\d+)',href,re.I):
            try:links.append(source_url(href,url))
            except ValueError:issues.append(dict(card=0,code='INVALID_DISCOVERY_URL'))
    if not cards and not links:issues.append(dict(card=0,code='UNRECOGNIZED_OR_EMPTY_HTML'))
    return dict(records=records,rows=rows,issues=issues,links=list(dict.fromkeys(links)),cards=len(cards))


def fixture(model):
    if model not in ROOTS:raise ValueError('UNSUPPORTED_MODEL')
    raw=(DIRECTORY/(model+'.json')).read_bytes()
    if len(raw)>MAX_ARTIFACT_BYTES:raise ValueError('FIXTURE_TOO_LARGE')
    value=json.loads(raw)
    if value['version']!=VERSION or value['synthetic'] is not True or value['model']!=model or not 1<=len(value['pages'])<=MAX_PAGES:raise ValueError('INVALID_FIXTURE_MANIFEST')
    return value,sha(raw)


def run_fixture(model,expected_sha,progress):
    manifest,checksum=fixture(model)
    if checksum!=expected_sha:raise ValueError('FIXTURE_CHANGED')
    pages={source_url(p['url']):p for p in manifest['pages']}
    if len(pages)!=len(manifest['pages']):raise ValueError('DUPLICATE_PAGE')
    queue=[ROOTS[model]];visited=set();records=[];rows=[];issues=[];found=0
    progress(0,None,'pages')
    while queue:
        progress(len(visited),None,'pages')
        url=queue.pop(0)
        if url in visited:continue
        if url not in pages:issues.append(dict(page=url,code='MISSING_FIXTURE_PAGE'));continue
        if len(visited)>=MAX_PAGES:raise ValueError('PAGE_LIMIT')
        p=pages[url]
        parsed=parse_page(p['html'],url,p['observed_at'],model);visited.add(url);found+=parsed['cards']
        records.extend(parsed['records']);rows.extend(parsed['rows']);issues.extend(dict(page=url,**i) for i in parsed['issues'])
        if len(records)>MAX_RECORDS:raise ValueError('RECORD_LIMIT')
        queue.extend(link for link in parsed['links'] if link not in visited and link not in queue)
    unique={};duplicates=conflicts=0
    for row in rows:
        # Model/category associations are kept; only identical observations collapse.
        key=(row['source_article'],row['model'],row['category'],row['subcategory'])
        old=unique.get(key)
        if old:
            comparable=lambda r:{k:v for k,v in r.items() if k!='source_record'}
            if comparable(old)!=comparable(row):
                conflicts+=1;issues.append(dict(code='CONFLICTING_OBSERVATION',article=row['source_article']));unique[key]=None
            else:duplicates+=1
        elif key not in unique:unique[key]=row
    # Any conflict for an article blocks all its associations, never last-write-wins.
    blocked={key[0] for key,value in unique.items() if value is None}
    observations={}
    for row in rows:
        core={k:row[k] for k in ('part_name','oem','condition','price_uah','price_usd','source_url','observed_at')}
        old=observations.setdefault(row['source_article'],core)
        if old!=core and row['source_article'] not in blocked:
            blocked.add(row['source_article']);conflicts+=1;issues.append(dict(code='CONFLICTING_OBSERVATION',article=row['source_article']))
    output=[r for k,r in unique.items() if r and k[0] not in blocked]
    by_article={r['source_article']:r for r in output}
    summary=dict(data_source='synthetic_offline_fixture',live=False,adapter_version=VERSION,fixture_sha256=checksum,pages_checked=len(visited),offers_found=len({r['article'] for r in records}),cards_found=found,exportable_offers=len(by_article),with_prices=sum(r['price_uah'] is not None or r['price_usd'] is not None for r in by_article.values()),with_oem=sum(bool(r['oem']) for r in by_article.values()),duplicates=duplicates,conflicts=conflicts,error_count=len(issues),skipped_records=found-len(rows)+sum(1 for r in rows if r['source_article'] in blocked),collection_completeness='fixture_pages_complete' if not issues and len(visited)==len(pages) else 'partial_fixture',live_collection_completeness='unverified',issues=issues[:20],issues_truncated=len(issues)>20,committed=False)
    artifact=encoded(dict(schema_version='r83-result-1',synthetic=True,summary=summary,records=records,rows=output))
    if len(artifact)>MAX_ARTIFACT_BYTES:raise ValueError('ARTIFACT_STORAGE_LIMIT')
    progress(len(visited),None,'pages')
    return summary,artifact
