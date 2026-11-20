"""Read-only OEM diagnosis and missing-year guard, no provider calls."""
from types import SimpleNamespace
from app.services import auto_oem


def _vehicle(**overrides):
    defaults=dict(
        manufacturer="Volvo", model="XC90", year=None, vin=None,
        engine_code="B4204T27", engine_variant=None,
        engine_displacement_l=None, generation="",
        drive_type="AWD", fuel_type="Gasoline", dismantling_v3={},
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_missing_year_does_not_crash_oem_pilot_or_directory():
    car=_vehicle()
    assert auto_oem.source_identity(car) is None
    class ForbiddenAdapter:
        def directory(self,**kwargs):
            raise AssertionError("No Catalogue network for unknown year")
    cache=auto_oem.SourceCache(adapter=ForbiddenAdapter())
    assert cache.resolve_directory(car) is None


def test_known_pilot_requires_real_source_evidence():
    car=_vehicle(year=2016,vin="YV4A22PK2G1092943")
    assert auto_oem.source_identity(car) == (107555,13084,120,None,False)


def test_oem_audit_denies_non_admin_and_does_not_call_provider(logged,monkeypatch):
    from app.api import oem_diagnostics as route
    monkeypatch.setattr(route,"platform_admin",lambda _user:False)
    monkeypatch.setattr(route,"audit",lambda _db: (_ for _ in ()).throw(AssertionError("audit called")))
    r=logged.get("/api/v1/oem/admin/coverage")
    assert r.status_code==403


def test_oem_audit_is_read_only_and_reports_missing_source(logged,monkeypatch):
    from app.api import oem_diagnostics as route
    monkeypatch.setattr(route,"platform_admin",lambda _user:True)
    data={
        "manufacturer":"DAF","model":"XF","year":2007,
        "donor_id":"OEM-DAF-1","vin":"XLRTE47MS0E774889",
        "acquisition_cost":"0.00",
    }
    saved=logged.post("/api/v1/vehicles",json=data)
    assert saved.status_code==201,saved.text
    r=logged.get("/api/v1/oem/admin/coverage")
    assert r.status_code==200,r.text
    result=r.json()
    assert result["read_only"] is True
    assert result["external_requests"] == 0
    assert result["provider_credits"] == 0
    daf=next(x for x in result["vehicles"] if x["model"]=="DAF XF")
    assert daf["counts"]["vehicles"] == 1
    assert daf["counts"]["valid_oem_refs"] == 0
    assert daf["counts"]["eligible_rows_without_oem_ref"] == 0
    assert daf["counts"]["stock_linked_to_dismantling_row"] == 0
    assert daf["counts"]["stock_linked_valid_oem_ref_without_oem"] == 0
    assert daf["counts"]["stock_manual_oem_clear"] == 0
    assert daf["reasons"]["missing_exact_engine_code_and_modification"] == 1


def test_workspace_stock_report_counts_visible_card_and_manual_selection(logged, part, monkeypatch):
    from app.api import oem_diagnostics as route

    monkeypatch.setattr(route,'platform_admin',lambda user:True)
    response=logged.post('/api/v1/parts/'+part['id']+'/operations',json={
        'type':'receipt','quantity':1,'reason':'Coverage test',
    })
    assert response.status_code==200,response.text
    response=logged.patch('/api/v1/parts/'+part['id']+'/characteristics',json={
        'expected':{'oem_number':''},'values':{'oem_number':'MANUAL-EXAMPLE'},
    })
    assert response.status_code==200,response.text
    report=logged.get('/api/v1/oem/admin/coverage?workspace_stock=true')
    assert report.status_code==200,report.text
    assert report.json()['stock']=={'positions':1,'with_oem':1,'manual_oem':1,'coverage_percent':100.0}
