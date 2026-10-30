"""Stage B: persistence, versions, race tokens (F23–F31)."""

from osint_agent.api.market import set_repo
from osint_agent.market.repository import MarketRepository
from osint_agent.market.auto_analysis import build_auto_analysis


def _summary(inn="7707083893"):
    return build_auto_analysis(
        {"inn": inn, "name": "X", "okved_main": "64.19"},
        {"years": [{"year": 2020, "revenue": 1, "net_profit": 0}, {"year": 2021, "revenue": 10, "net_profit": 2}]},
        {"contracts": {"items": [{"id": "c1", "fields": {"Заказчик": "A"}, "amount": 5}]}},
    )


def test_f23_versions_survive_reconnect(tmp_path):
    db = tmp_path / "m.db"
    repo = MarketRepository(db)
    v1 = repo.save_analysis_version(_summary(), request_key="k1")
    repo.close()
    # «перезапуск»
    repo2 = MarketRepository(db)
    loaded = repo2.latest_analysis_for(legal_entity_inn="7707083893")
    assert loaded is not None
    assert loaded["analysis_version_id"] == v1["analysis_version_id"]
    assert loaded["report_version"] == 1
    assert loaded["limitations"]
    repo2.close()


def test_f30_new_failed_keeps_old_version(tmp_path):
    repo = MarketRepository(tmp_path / "m.db")
    v1 = repo.save_analysis_version(_summary(), status="completed")
    v2 = repo.save_analysis_version(_summary(), status="partial")
    assert v2["report_version"] == 2
    old = repo.get_analysis_version(v1["analysis_version_id"])
    assert old["report_version"] == 1
    repo.close()


def test_f24_job_recorded(tmp_path):
    repo = MarketRepository(tmp_path / "m.db")
    job = repo.create_job(kind="auto_analysis", legal_entity_inn="1", owner_token="tok-1")
    assert job["status"] == "running"
    saved = repo.save_analysis_version(_summary(), request_key="tok-1")
    repo.finish_job(job["id"], status="completed", result_version_id=saved["analysis_version_id"])
    row = repo.job_by_token("tok-1")
    assert row["status"] == "completed"
    assert row["result_version_id"] == saved["analysis_version_id"]
    repo.close()


def test_f31_export_uses_saved_version(tmp_path):
    repo = MarketRepository(tmp_path / "m.db")
    v = repo.save_analysis_version(_summary())
    # экспорт читает ту же версию
    again = repo.get_analysis_version(v["analysis_version_id"])
    assert again["evidence_refs"] == v["evidence_refs"]
    assert again["finance_summary"]["latest_year"]["year"] == v["finance_summary"]["latest_year"]["year"]
    repo.close()


def test_f29_two_products_separate_studies(tmp_path):
    repo = MarketRepository(tmp_path / "m.db")
    from osint_agent.market.models import MarketScope, StudyPassport

    a = StudyPassport(title="P1", scope=MarketScope(product="P1"))
    b = StudyPassport(title="P2", scope=MarketScope(product="P2"))
    repo.create_study(a)
    repo.create_study(b)
    s1 = _summary()
    s1["study_id"] = str(a.id)
    s2 = _summary()
    s2["study_id"] = str(b.id)
    repo.save_analysis_version(s1)
    repo.save_analysis_version(s2)
    assert repo.latest_analysis_for(study_id=str(a.id))["study_id"] == str(a.id)
    assert repo.latest_analysis_for(study_id=str(b.id))["study_id"] == str(b.id)
    repo.close()
