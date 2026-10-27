"""Central, fail-closed route policy. Workspace and actor are always server-derived."""
from fastapi import HTTPException
from app.route_registry import KNOWN_ROUTES
GROUPS={
 'Склад':{'inventory.view':'Перегляд складу','inventory.create':'Додавання деталей','inventory.edit':'Редагування деталей','inventory.archive':'Архівування та відновлення','inventory.adjust_quantity':'Коригування кількості','inventory.write_off':'Списання','inventory.transfer':'Переміщення','inventory.reserve':'Ручне резервування','parts.notes':'Внутрішні нотатки','parts.inspect':'Стан і перевірка','parts.change_price':'Зміна ціни'},
 'Фінанси':{'parts.view_cost':'Собівартість і витрати','sales.view_financials':'Фінансові дані продажів та замовлень'},
 'Продажі':{'sales.view':'Перегляд продажів','sales.create':'Проведення продажів'},
 'Замовлення':{'orders.view':'Перегляд замовлень і покупців','orders.create':'Створення замовлень','orders.edit':'Редагування замовлень','orders.fulfill':'Резервування та виконання замовлень'},
 'Автомобілі':{'vehicles.view':'Перегляд автомобілів','vehicles.create':'Додавання автомобілів','vehicles.edit':'Редагування автомобілів','dismantling.manage':'План розбору','catalog.view':'Перегляд довідника','catalog.import':'Імпорт каталогу'},
 'Аналітика':{'analytics.view':'Статистика залишків','analytics.financial':'Фінансова аналітика','audit.view':'Історія операцій'},
 'Команда':{'team.view':'Перегляд команди','team.manage_managers':'Керування менеджерами'},
 'Налаштування':{'settings.manage':'Налаштування складу'},
}
PERMISSIONS={k:v for group in GROUPS.values() for k,v in group.items()}
DEFAULT_EMPLOYEE=['inventory.view','vehicles.view','catalog.view']

def effective(user):
    rights=frozenset(PERMISSIONS) if user.role=='DIRECTOR' else frozenset(user.permissions)&PERMISSIONS.keys()
    return rights-{'team.manage_managers'} if user.role=='MANAGER' else rights
def require_permission(who,*permissions):
    if not set(permissions)<=who.permissions:raise HTTPException(403,'Недостатньо прав для цієї дії. Зверніться до директора')
def require_director(who):
    if who.user.role!='DIRECTOR':raise HTTPException(403,'Дія доступна лише директору')
def require_workspace_access(who,workspace):
    if workspace!=who.workspace_account_id:raise HTTPException(404,'Запис не знайдено')

def route_permissions(method,path,body):
    if (method,path) not in KNOWN_ROUTES:return ['__deny__']
    path=path.removeprefix('/api/v1');read=method=='GET'
    if path in ('/auth/me','/auth/logout','/auth/password') or path in {'/team/readiness','/smart-search/readiness','/workshop/readiness','/orders/readiness','/sales-workspace/readiness','/vehicle-view/readiness','/dismantling/readiness','/dismantling/workspace-readiness','/dismantling/simple-readiness'}:return []
    if path=='/catalogue/capabilities' or path.startswith('/catalogue/admin/'):
        return []  # Admin endpoints independently require the platform allowlist.
    if path=='/catalogue' or path.startswith('/catalogue/'):
        return ['catalog.view']
    if path.startswith('/team'):return ['team.view'] if read else ['team.manage_managers']
    if path in ('/parts','/inventory') and read:return ['inventory.view']
    if path=='/parts/bulk-actions':return ['inventory.transfer' if body.get('action')=='transfer' else 'inventory.archive']
    if path=='/parts' and method=='POST':return ['inventory.create']
    if path.startswith('/parts/'):
        if read:return ['inventory.view']
        if path.endswith('/price'):return ['parts.change_price']
        if path.endswith('/notes'):return ['parts.notes']
        if path.endswith('/inspection'):return ['parts.inspect']
        if path.endswith('/operations'):
            return [{'sale':'sales.create','write_off':'inventory.write_off','transfer':'inventory.transfer','reserve':'inventory.reserve','release':'inventory.reserve','receipt':'inventory.adjust_quantity','correction':'inventory.adjust_quantity'}.get(body.get('type'),'__deny__')]
        return ['inventory.edit']
    if path.startswith('/photos/'):return ['inventory.view']
    if path.startswith('/archive'):return ['inventory.view','inventory.archive']
    if path.startswith('/smart-search/'):return ['inventory.view']
    if path.startswith('/plan-parts/'):return ['vehicles.create']
    if path.startswith('/dismantling/catalog/'):return ['catalog.import']
    if path=='/vehicle-catalog':return ['vehicles.view']
    if path.endswith('/aleto-catalog'):return ['vehicles.view','catalog.view']
    if path.startswith('/vehicles'):
        if '/analytics' in path:return ['analytics.view']
        if '/dismantling' in path or '/checklist' in path or '/plan-parts-checklist' in path:
            if read:return ['vehicles.view','catalog.view']
            receive=path.endswith('/add-stock') or (body.get('action')=='receipt') or (path.endswith('/checklist'))
            return ['dismantling.manage','inventory.create','inventory.adjust_quantity'] if receive else ['dismantling.manage']
        return ['vehicles.view'] if read else ['vehicles.create' if path=='/vehicles' else 'vehicles.edit']
    if path.startswith('/categories'):return ['catalog.view' if read else 'catalog.import']
    if path.startswith('/buyers'):return ['orders.view' if read else 'orders.create' if path=='/buyers' else 'orders.edit']
    if path.startswith('/orders'):
        if read:return ['orders.view']
        if path=='/orders':return ['orders.create']
        if path.endswith('/{action}'):return ['orders.fulfill']+(['sales.create'] if body.get('_route_action')=='sell' else [])
        return ['orders.edit']
    if path=='/sales/summary':return ['analytics.view','analytics.financial','sales.view','sales.view_financials']
    if path=='/sales':return ['sales.view']
    if path=='/dashboard':return ['analytics.view']
    if path=='/audit':return ['audit.view']
    if path=='/settings':return [] # Read-only personal profile and public feature flags.
    return ['__deny__']

def check_fields(who,path,body):
    # Full replacement forms must not reset protected values via omitted defaults.
    if path in ('/api/v1/parts','/api/v1/parts/{id}'):
        if 'unit_cost' in body:require_permission(who,'parts.view_cost')
        for field,permission in [('internal_notes','parts.notes'),('condition','parts.inspect'),('availability','parts.inspect'),('location','inventory.transfer'),('vehicle_id','vehicles.view'),('category_id','catalog.view'),('subcategory_id','catalog.view')]:
            if field in body:require_permission(who,permission)
        if 'selling_price' in body or 'currency' in body:require_permission(who,'parts.change_price')
    if path.startswith('/api/v1/vehicles') and 'acquisition_cost' in body:require_permission(who,'parts.view_cost')

COST={'unit_cost','acquisition_cost','allocated_parts_cost','potential_gross_margin','margin_positions','vehicle_acquisition_cost'}
FINANCE={'sale','unit_price','line_total','totals_by_currency','sale_price','sale_currency','price_recorded'}
ANALYTICS={'vehicle_valuation_by_currency','valuation_by_currency','estimated_sales_value','by_vehicle'}
def redact(value,permissions,*,path='',nested=False):
    if isinstance(value,list):return [redact(v,permissions,path=path,nested=True) for v in value]
    if not isinstance(value,dict):return value
    result={}
    for key,item in value.items():
        if key=='recent_operations' and 'audit.view' not in permissions:continue
        if key in COST and 'parts.view_cost' not in permissions:continue
        if key in FINANCE and 'sales.view_financials' not in permissions:continue
        if (key in ANALYTICS or key in COST-{'unit_cost','acquisition_cost'}) and 'analytics.financial' not in permissions:continue
        if key=='value' and 'analytics.financial' not in permissions:continue
        if key=='total' and nested and 'sales.view_financials' not in permissions:continue
        result[key]=redact(item,permissions,path=path,nested=True)
    return result
