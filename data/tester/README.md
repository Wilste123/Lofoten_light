# Tester (.fit)

Sykkel/løp-tester lastes hit fra **`rethink`**-branchen (`Tester/`) eller manuelt.

```bash
git show origin/rethink:Tester/FTP_sykkel_03_11_2026.fit > data/tester/FTP_sykkel_03_11_2026.fit
python3 scripts/read_fit_activity.py data/tester/FTP_sykkel_03_11_2026.fit
```

Oppdater `docs/athlete/profile.md` etter valid FTP/terskel-test.
