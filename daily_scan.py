from scanner_core import ScanConfig, append_audit_log, run_scan, write_outputs

if __name__ == "__main__":
    cfg = ScanConfig(lookback="2y", min_obs=140, benchmark="SPY", output_dir="output")
    results = run_scan("config/universe.csv", cfg)
    write_outputs(results, cfg.output_dir)
    append_audit_log(results, "output/feature_history.csv")
    print(f"Scanned {len(results['stocks'])} securities across {results['stocks']['theme'].nunique()} themes.")
    print(results['registry'].head(20).to_string(index=False))
