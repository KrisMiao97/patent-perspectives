# Filing-date analysis windows

A run may set `scope.analysis_window` to
`{"basis":"filing_date","from":"START_DATE","through":"END_DATE"}`.
Both endpoints are inclusive. This selects an analysis cohort from the existing
candidate population; it does not change the global publication cutoff, company
boundary, search totals, identity decisions, source documents or historical data.

The standard-library `scripts/derive_scope.py` defaults to inspection only:

```
python scripts/derive_scope.py --parent RUN/full.sqlite --from START_DATE --through END_DATE --report-dir RUN/recent5y-scope-review
```

Review `cohort-summary.json`, `date-anomalies.json` and source-bound
`temporal-decisions.jsonl`. Explicit `--create --output RUN/recent5y.sqlite`
creates a **new** complete SQLite backup in the same directory. Existing output
files are refused. Keeping both databases in that folder preserves relative
source/cache paths. The child has a new run ID, `parent_run_id`, complete parent
scope and row-count provenance. No SQL deletion is used. Role conclusions retain
their existing evidence and population hashes; parent-wide conclusions must be
regenerated for the child cohort before formal delivery.

Every retained application, publication-version and bibliography filing date is
considered. Raw date fields and historical conflict values are retained in the
decision evidence. Publication, priority and national-entry dates are not
substituted. No date or a malformed nonempty observation is `pending`; conflicting
values crossing the window are also `pending`. If every observed filing date is
inside the window, membership is `included`, while a conflicting exact date is
`unknown` for date statistics. If every observed value is outside, membership is
`outside`, while all records remain stored. Missing fields in one source do not
contradict an explicit date in another source.

Group identity and temporal membership are separate decisions. An identity
exclusion stays excluded even when its filing date falls inside. Coverage keeps
the parent candidate and identity counts and additionally exposes the selected
cohort, type counts, pending dates and cross-counts under `analysis_window`.
Technical coverage and completion gates use only the selected cohort; pending
dates that could affect membership prevent child completion. Dates, identity and
ownership remain distinct: window membership does not establish control at
filing or current ownership.

命令中的START_DATE、END_DATE分别替换为用户确认的YYYY-MM-DD日期。
