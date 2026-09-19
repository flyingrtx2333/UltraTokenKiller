from ultratokenkiller.benchmark import capability_report, run_benchmark


def test_offline_report_is_metadata_only_and_honest():
    for mode in ("passthrough", "prototype", "native"):
        report = run_benchmark(mode)
        assert report["status"] == "completed"
        assert report["live_model_calls"] == 0
        assert report["parity_certified"] is False
        assert len(report["cases"]) >= 6
        assert all(item["required_facts_preserved"] for item in report["cases"])
        assert all("content" not in item["engine"] for item in report["cases"])
    assert run_benchmark("upstream")["status"] == "not_run"


def test_inventory_does_not_claim_unreviewed_variants_complete():
    report = capability_report()
    assert report["discovered_command_variants"] > 100
    assert report["reviewed_command_variants"] == 0
    assert report["parity_certified"] is False
