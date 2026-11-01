# Trend Detective: System Design and Architecture

NASA Space Apps Challenge 2026 | Challenge: Be an Earth System Trend Detective | Team of 4 (React, Python, ML/DL) | Version 1.0

'Trend Detective' is a working title. Rename it freely.

## 1. What we are building

A web tool that lets a student or curious citizen act as a data detective. They choose an Earth science variable, choose a region, and the tool shows how that variable changed over time, how fast, and whether the change is statistically significant.

The challenge asks for four things. This is how each one maps to our system:

| Challenge requirement | Our feature | Module |
| --- | --- | --- |
| 1. Identify variables worth investigating | Variable catalog with plain-language definitions, plus a short guided question flow that suggests variables | Catalog service, Suggest service |
| 2. Acquire data for a particular region | Region picker (presets, country, drawn box) and a data layer that subsets NASA data to that region | Region service, Data layer |
| 3. Visualize a long time series | Interactive monthly time series (raw and deseasonalized), 10 to 25 years | Timeseries service, charts |
| 4. Basic statistics: rate of change and significance | Mann-Kendall test, Sen's slope with 95% confidence interval, OLS and t-test cross-check, plain-language verdict | Analysis engine |

The statement also says we must answer four questions. Here is where each answer appears in the UI:

- **What is changing?** The variable and the direction of the trend.
- **Where is it changing?** The region, plus an optional trend map showing the slope per grid cell.
- **How much is it changing?** Slope per decade, percent change per decade, and total change over the period.
- **Is it significant?** p-value, confidence interval, and a clear verdict label.

## 2. Design principles

1. **Statistics first.** The core deliverable is the trend and significance result. Everything else supports it.
2. **Data-source agnostic.** The official resources are released on Friday, November 13, the day before the event. The system must work with any gridded monthly dataset by adding a catalog entry, not by rewriting code.
3. **Reliable demo.** Every featured variable and region is precomputed and cached, so the demo never depends on NASA servers being fast.
4. **Scientifically honest.** We report trends, not causes, and we do not forecast. Every result shows its data source, period, method, and caveats.
5. **Plain language.** The audience is high school and college students and the public. Every variable, number, and test result gets a short explanation.
6. **Small enough to finish.** Four people, about two weeks of preparation, then 48 hours.

## 3. Scope tiers

**MVP (must ship):**

- Variable catalog with at least 6 variables and plain-language definitions
- Region selection: Bangladesh, its 8 divisions, and a drawn custom box
- Monthly time series chart with a trend line
- Mann-Kendall test, Sen's slope with 95% CI, p-value, verdict, and caveats
- Methods and data-sources page
- Deployed, with cached data for all featured variables and regions

**Should ship:**

- Guided 'detective' question flow that suggests variables
- Two-region comparison (the statement stresses that trends can go opposite ways in different places)
- Trend map: slope per grid cell with significance marking
- Export of CSV and chart image
- Bangla and English interface toggle

**Stretch (only if time remains):**

- Change-point detection (when did the trend shift?)
- Live fetch of any variable for any region via NASA services
- Optional LLM explainer, constrained to computed numbers
- Shareable report page or PDF

## 4. User journey

1. **Landing.** One sentence about the challenge, one button: Start investigating.
2. **Ask.** Three short questions: What are you curious about (water, heat, plants and land, air)? Where? How far back should we look? Answers narrow the variable list. A 'browse all variables' link skips the questions.
3. **Pick a variable.** Cards show the name, a one-line definition, units, source mission, and the years available.
4. **Pick a region.** Map with presets, a country list, or a drawn rectangle. The tool shows the region area and how many data grid cells it contains.
5. **Results.** Time series chart (raw, deseasonalized, trend line with confidence band) and a stats panel: slope per decade, percent change, p-value, verdict, and a plain-language paragraph with caveats.
6. **Go deeper.** Compare with another region, view the trend map, change the date range, or export.
7. **Methods.** Always one click away: what the tests mean, data credits, limitations.

Result URLs carry the choices as query parameters (variable, region, start, end), so any result can be shared or bookmarked.

## 5. System architecture

```
  [ Browser: React single-page app ]
     wizard | charts | map | compare | methods
              |  HTTPS, JSON
              v
  [ FastAPI backend ]  (stateless)
     routers: variables | suggest | regions | timeseries | trend | compare | trend-map | jobs | export
        |            |               |                 |
        v            v               v                 v
   Catalog      Region          Analysis           Explain
   service      service         engine             service
        \           |               |                /
         \          v               v               /
          +-----> Data access layer (adapters) <---+
                     |                 |
                     v                 v
          [ Cache: Parquet + NetCDF ]  [ Live fetch via earthaccess / OPeNDAP ]
                     ^                 |
                     |                 v
          [ Offline ETL pipeline ] <--- [ NASA Earthdata: GES DISC, LP DAAC ]
```

**Components:**

| Component | Responsibility | Tech |
| --- | --- | --- |
| React SPA | Wizard, charts, map, compare, methods pages, i18n | React, Vite, Tailwind, Plotly.js, Leaflet or MapLibre, React Query |
| FastAPI backend | REST API, validation, caching, job status, OpenAPI docs | Python 3.11+, FastAPI, Pydantic, Uvicorn |
| Catalog service | Reads the variable catalog (YAML), serves definitions and metadata | PyYAML, Pydantic |
| Suggest service | Maps user answers to ranked variables | Rule-based first, embeddings later |
| Region service | Loads boundaries, validates custom boxes, builds masks | GeoPandas, Shapely, regionmask |
| Data access layer | One interface for all datasets; reads cache first, live fetch second | xarray, earthaccess, netCDF4, pandas, pyarrow |
| Analysis engine | Deseasonalizing, trend tests, confidence intervals, quality warnings | NumPy, SciPy, statsmodels, pymannkendall |
| Explain service | Turns numbers into plain-language text from templates | Python string templates (LLM optional) |
| Offline ETL | Downloads and subsets NASA data, builds the cache | Python scripts, earthaccess, xarray |
| Cache | Region-averaged monthly series as Parquet; gridded subsets as NetCDF or Zarr | Files in the repo or object storage |

**Request flow, cached (normal path):** The SPA calls POST /trend. The backend validates the request, asks the Data access layer for the series, finds it in cache, runs the Analysis engine, builds the explanation, and returns JSON in well under 2 seconds.

**Request flow, live (stretch):** If the series is not cached, the backend starts a job, returns a job id, and the SPA polls GET /jobs/{id}. The job subsets the NASA data, stores the result in cache, and then the normal flow completes. If NASA is unreachable, the API returns a clear error and offers the nearest cached alternative.

The backend is stateless and has no user accounts. The only stored state is the cache and the job table (in memory is fine for a hackathon).

## 6. Data layer

### 6.1 Candidate variables

The statement names MODIS, OMI, AIRS, GPM, MERRA-2, and GLDAS. The table below is our starting candidate set. **Product names, versions, and date ranges below are from general knowledge and must be verified against the official resources released on November 13.** The architecture does not depend on any single one.

| Variable (plain name) | Likely source | Approx. resolution | Approx. record | Notes |
| --- | --- | --- | --- | --- |
| Rainfall (precipitation) | GPM IMERG monthly | 0.1 degrees | 2000 to present | Core variable for Bangladesh |
| Air temperature at 2 m | MERRA-2 monthly | about 0.5 x 0.625 degrees | 1980 to present | Longest record; coarse grid |
| Land surface temperature | MODIS monthly, or GLDAS | 0.05 to 0.25 degrees | 2000 to present | MODIS has cloud gaps |
| Vegetation greenness (NDVI) | MODIS monthly | 0.05 degrees | 2000 to present | Seasonal; deseasonalize carefully |
| Soil moisture | GLDAS monthly | 0.25 degrees | 2000 to present | Model-based |
| Evapotranspiration | GLDAS monthly | 0.25 degrees | 2000 to present | Mentioned in the statement as a harder variable |
| Ozone, other atmospheric variables | OMI, AIRS | varies | varies | Add later if time allows |

Start the MVP with 4 to 6 of these. More variables are cheap once the pipeline works: one catalog entry plus one ETL run each.

### 6.2 Access methods

- **Primary (offline ETL):** the `earthaccess` Python library for Earthdata login, search, and download or streaming, then `xarray` to subset by region and time.
- **Alternative:** OPeNDAP access to NASA data servers, opened directly with `xarray`.
- **Cross-check:** NASA Giovanni, which produces area-averaged time series in the browser. Use it to verify our numbers for 2 or 3 variables before the demo. Matching Giovanni is strong evidence the pipeline is right.
- **Credentials:** every team member needs an Earthdata account. Tokens live in environment variables, never in the frontend or the repository.

### 6.3 ETL pipeline (offline, run by the data engineer)

For each variable in the catalog:

1. **Download or stream** monthly files for the full record and a bounding box around the target region.
2. **Standardize.** Rename coordinates to lat, lon, time. Convert units (for example Kelvin to Celsius, mm per hour to mm per month). Record the unit in the catalog.
3. **Mask and average.** For each preset region, compute an area-weighted mean (weights proportional to cosine of latitude) over cells inside the region.
4. **Monthly series.** One row per month: date, value, number of valid cells, fraction of missing cells.
5. **Save.** Region-averaged series to Parquet (small, instant to load). Gridded subset for Bangladesh and surrounding area to NetCDF or Zarr (for the trend map).
6. **Quality report.** For each series: first and last date, number of gaps, missing fraction, and min and max. Save it next to the data.

### 6.4 Storage layout

```
data/
  catalog/variables.yaml          # one entry per variable
  regions/bangladesh_divisions.geojson
  cache/series/{variable_id}/{region_id}.parquet
  cache/grids/{variable_id}.zarr  # or .nc
  reports/{variable_id}_quality.json
```

The Bangladesh dataset is small. All of this fits in the repository or a free object store.

### 6.5 Regions

- **Presets:** Bangladesh, the 8 administrative divisions (Dhaka, Chattogram, Rajshahi, Khulna, Barishal, Sylhet, Rangpur, Mymensingh), and optionally a few meaningful areas (coastal belt, Sundarbans area, Haor basin, Chittagong Hill Tracts).
- **Country list:** from an open boundary dataset (check the license of whichever you use; Natural Earth is public domain, geoBoundaries is open, and GADM has usage restrictions).
- **Custom box:** drawn on the map; the server validates it.
- **Grid-cell rule:** a region must contain a minimum number of dataset grid cells, for example 4. A coarse dataset like MERRA-2 cannot meaningfully describe a small district. If the rule fails, return a clear message that suggests a larger region or a finer dataset.

### 6.6 Data quality rules

- Never silently fill gaps. Short gaps of 3 months or fewer may be interpolated and flagged; longer gaps stay missing.
- If more than 20 percent of months are missing, return a warning with the result.
- Record length below 10 years: show a warning. Below 5 years: refuse to run the test.
- Always show the source product, version, units, and period on the result.

## 7. Analysis engine

This is the most important module. It should be a plain Python package with no web dependencies, so it can be tested alone.

### 7.1 Inputs and outputs

Input: a monthly time series (date, value) plus options (alpha, deseasonalize on or off). Output: processed series, trend statistics, cross-check statistics, and a list of warnings.

### 7.2 Steps

1. **Validate.** Check length, gaps, and monotonic dates (rules in 6.6).
2. **Deseasonalize.** Compute the monthly climatology (mean of each calendar month over the period) and subtract it, giving anomalies. This is essential. Without it, strong seasonal cycles such as the monsoon distort trend tests.
3. **Primary trend test.** Mann-Kendall test on the monthly anomalies. Use the Hamed and Rao modification (available in `pymannkendall`) to correct for autocorrelation, which is common in climate series.
4. **Rate of change.** Sen's slope (median of pairwise slopes) with a 95 percent confidence interval. Convert to units per decade.
5. **Cross-check.** Fit ordinary least squares on annual means and run the t-test on the slope (the statement names the t-test). Report whether the two methods agree on direction and significance.
6. **Effect size.** Total change over the period (slope times duration) and percent change per decade relative to the mean. For variables where a percent is misleading (such as temperature in Celsius), show absolute change only.
7. **Verdict.** Map to a label using alpha = 0.05:
   - Significant increasing trend
   - Significant decreasing trend
   - No significant trend
   - Inconclusive (short record, too many gaps, or the two methods disagree)
8. **Warnings.** Short record, many gaps, autocorrelation detected, methods disagree, region contains few grid cells.

### 7.3 Caveats shown to users

- Significant means unlikely to be random variation. It does not mean important or caused by a particular process.
- A trend over this period may not continue and is not a forecast.
- Data from models (MERRA-2, GLDAS) combine observations and physics, so they are estimates.
- A region average can hide opposite trends inside the region. The trend map helps show this.

### 7.4 Trend map (Should)

For each grid cell inside the region, compute Sen's slope and a Mann-Kendall p-value on that cell's deseasonalized series. Mark cells where p is below 0.05. Because many cells are tested at once, apply a false discovery rate correction (Benjamini-Hochberg via `statsmodels`) before marking significance, and say so on the Methods page. Precompute for the Bangladesh grid; for custom regions, run asynchronously.

## 8. Backend API

Base path /api/v1. FastAPI generates OpenAPI docs automatically. The frontend and backend agree on this contract first (section 14).

| Method and path | Purpose |
| --- | --- |
| GET /health | Liveness check |
| GET /variables | List catalog (filter by category or text) |
| GET /variables/{id} | Definition, units, source, record span, resolution |
| POST /suggest | Answers to the guided questions in, ranked variables out |
| GET /regions | Preset regions with ids and geometry |
| POST /regions/validate | Check a custom box: area, number of grid cells, usable or not |
| POST /timeseries | Series for a variable, region, and range |
| POST /trend | Series plus full statistics and explanation |
| POST /compare | Two regions, same variable: both results and a plain-language comparison |
| POST /trend-map | Per-cell slope and significance for a region |
| GET /jobs/{id} | Status and result of an asynchronous task |
| POST /export | CSV or JSON export of a result |
| GET /methods | Method text and data credits |

**POST /trend request shape:**

```
variable_id: precip_monthly
region: { type: preset, id: bd_dhaka }     # or { type: bbox, coords: [west, south, east, north] }
start: 2001-01
end: 2025-12
options: { deseasonalize: true, alpha: 0.05 }
```

**Response shape:**

```
meta: { variable, region, source, units, n_months, missing_pct, warnings: [] }
series: [ { date, value, anomaly } ... ]
trend: { method, tau, p_value, slope_per_decade, slope_ci95: [low, high],
         pct_change_per_decade, total_change, direction, significant, verdict }
crosscheck: { ols_slope_per_decade, ols_p_value, agrees }
explanation: { headline, plain_text, caveats: [] }
```

**Errors:** 400 for invalid input, 422 for a region that is too small for the dataset or a series that is too short (with a helpful message), 503 if live fetch fails (with fallback suggestion). Error bodies always have a code and a human-readable message the UI can show directly.

## 9. Data models

**Variable catalog entry (YAML):**

| Field | Meaning |
| --- | --- |
| id | Unique key, for example precip\_monthly |
| name, name\_bn | Display names in English and Bangla |
| category | water, heat, land, or air |
| definition, definition\_bn | One or two plain sentences |
| units | Display units after conversion |
| source | Mission or model, product, version |
| record | Start and end of available data |
| resolution | Grid spacing |
| kind | observation or model |
| aggregation | How to average over a region (area-weighted mean) |
| percent\_change\_ok | Whether percent change is meaningful for this variable |
| keywords | Used by the Suggest service |

**Region:** id, name, type (country, division, area, bbox), geometry (GeoJSON), area in square kilometers.

**TrendResult:** as in the response shape above. The same object feeds the stats panel, the explanation, and the export.

## 10. Frontend

**Routes:** / (landing), /investigate (wizard), /results (results page, state in the URL), /compare, /explore (browse variables), /methods.

**Key components:** QuestionStep, VariableCard, RegionPicker (map with presets and draw tool), TimeSeriesChart (raw, anomaly, trend line, confidence band), StatsPanel, VerdictBadge, ExplanationBox, TrendMap, CompareView, ExportMenu, MethodsPage, LanguageToggle.

**State and data:** React Query for API calls and caching; the URL holds the investigation state; a small store (Zustand) is enough for the wizard.

**Charts:** Plotly.js handles time series with confidence bands and hover well. Use Leaflet or MapLibre for maps.

**UX rules:**

- Every statistic has a tooltip in plain language.
- The verdict is shown as a badge with words, not only color.
- Loading and error states for every request, with messages written for non-experts.
- Mobile-friendly layout, because many users will open it on a phone.
- Accessible: keyboard navigation, sufficient contrast, chart summaries in text.
- Bangla and English interface strings kept in translation files from day one.

## 11. Where ML and DL fit (honestly)

The challenge is a statistics problem. Mann-Kendall and Sen's slope are the right tools, and a neural network would not make them more correct. We should not force deep learning into the core. ML adds value in a few supporting places:

| Task | Approach | Priority |
| --- | --- | --- |
| Variable suggestion from user answers or free text | Keyword and rule matching first; sentence embeddings (small open model) for free-text questions later | Should |
| Plain-language explanation | Templates fill in the computed numbers. An LLM may rephrase, but must only use numbers from the result and never invent causes | Should (templates), Stretch (LLM) |
| Change-point detection | Pettitt test or the `ruptures` library to find when a trend shifted | Stretch |
| Anomaly and outlier flagging in input series | Simple robust statistics before any model | Should |

Recommended: the ML teammate owns the Suggest service, the Explain service, and the change-point stretch, and also helps validate the statistics. No forecasting models, since the challenge asks about past change.

## 12. Web app versus mobile app

**Recommendation: build a responsive web app, optionally installable as a PWA.** Reasons: you must use React and Python, and a React web app serves both desktop and phones with one codebase, deploys with a link judges can open instantly, and avoids app store review.

If you want a real mobile app:

- **React Native** reuses React skills but needs a separate UI codebase, native chart and map libraries, device testing, and build tooling. Expect roughly 40 to 60 percent more frontend work.
- Distribution is harder: judges would need an APK or TestFlight build, not just a link.
- The backend does not change at all. The API is already client-agnostic.

The pragmatic path: ship the web app, add a PWA manifest so it can be installed from the browser, and treat React Native as post-hackathon work. The architecture already supports it.

## 13. Repository, environments, deployment

```
trend-detective/
  README.md                  # setup, run, architecture summary
  docs/                      # this document, API contract, methods
  backend/
    app/ (main.py, routers/, services/, models/, core/config.py)
    analysis/                # pure-Python stats package, no web code
    tests/
    pyproject.toml
  etl/
    pipelines/, notebooks/   # one script per dataset
  data/ (catalog, regions, cache, reports)
  frontend/
    src/ (pages/, components/, api/, i18n/, hooks/)
    package.json
  docker-compose.yml
```

**Local development:** docker-compose starts the backend (port 8000) and frontend (port 5173). The frontend can also run against a mock server using fixture JSON, so frontend work never blocks on backend work.

**Deployment (free tiers, to be confirmed):** frontend on Vercel or Netlify; backend on Render, Railway, Fly.io, or Hugging Face Spaces in a Docker container. Free backends may sleep when idle, so open the app a few minutes before the demo. Cached data ships inside the backend image, so there is no database to set up.

**Configuration:** environment variables for the Earthdata token, allowed CORS origins, and the cache path. Provide a `.env.example`. Never commit secrets.

**Version control:** short-lived feature branches, pull requests reviewed by one teammate, and a protected main branch that always deploys.

## 14. Team split and interfaces

| Role | Owns | Main tasks |
| --- | --- | --- |
| P1 Frontend lead (React) | SPA | Wizard, charts, map, results page, compare view, i18n, responsive layout, UX copy |
| P2 Backend lead (Python) | API | FastAPI app, routers, validation, caching, jobs, OpenAPI, deployment, mock server |
| P3 Data engineer (Python) | Data layer | Earthdata access, ETL, region masks and boundaries, Parquet and grid cache, catalog YAML, data quality reports |
| P4 Stats and ML | Analysis and intelligence | Analysis engine, unit tests, Giovanni cross-check, Suggest and Explain services, change-point stretch |

Everyone: write the Methods page text together, and each person reviews one other person's pull requests.

**The contract comes first.** Before anyone builds in depth, agree on three artifacts: (1) the OpenAPI spec for the endpoints in section 8, (2) the catalog YAML schema in section 9, and (3) 3 to 4 fixture JSON responses for /trend. With these, the frontend, backend, data, and analysis work can proceed in parallel and meet cleanly.

## 15. Timeline

Today is Thursday, October 29. The event is Saturday and Sunday, November 14 and 15. Full resources are released Friday, November 13.

**Important:** check the official 2026 rules about what may be built before the event. Space Apps expects the project to be developed during the event, so treat earlier work as preparation: setup, learning, spikes, and shared contracts, and confirm with the rules or organizers what code you may bring in.

| Phase | Dates | Goals |
| --- | --- | --- |
| 0. Setup | Oct 30 to Nov 2 | Everyone has an Earthdata account; repo created; contracts agreed (OpenAPI, catalog schema, fixtures); each person runs a small spike in their area (one dataset download, one Mann-Kendall run, one chart on fixture data) |
| 1. Build the skeleton | Nov 3 to Nov 9 | End-to-end path on one variable: ETL to cache to analysis to API to chart. Test the analysis engine against known results. Draft Methods page |
| 2. Broaden | Nov 10 to Nov 12 | More variables, region presets, wizard UI, deploy a working version, rehearse |
| 3. Resources release | Nov 13 | Read the official resources and data links. Map them to catalog entries. Decide the final variable list. Verify product names and units |
| 4. Event | Nov 14 to Nov 15 | See below |

**During the 48 hours:**

| Block | Hours | Goals |
| --- | --- | --- |
| 1 | 0 to 6 | Ingest official datasets, finalize catalog, confirm everything works end to end with the official data |
| 2 | 6 to 18 | Complete MVP features: all variables, all regions, results page, verdict and explanations |
| 3 | 18 to 30 | Should-have features: guided questions, compare, trend map, export, Bangla toggle |
| 4 | 30 to 40 | Testing, bug fixing, Methods page, README, demo video or script |
| 5 | 40 to 46 | Feature freeze at about hour 40; polish only; final deploy; submission |
| Buffer | last 2 hours | Submission buffer. Confirm the exact submission deadline on the Space Apps site |

## 16. Testing and validation

- **Analysis engine unit tests:** synthetic series with a known slope plus noise (the test must recover the slope and detect significance); a pure-noise series (should report no significant trend most of the time); a pure seasonal cycle (should report no trend after deseasonalizing); series too short or full of gaps (should warn or refuse).
- **Cross-library check:** compare our Sen's slope and p-value with `scipy.stats.theilslopes`, `kendalltau`, and `pymannkendall` on the same data.
- **Scientific cross-check:** compare area-averaged series for 2 or 3 variables against NASA Giovanni. Record the comparison in the Methods page.
- **API tests:** each endpoint with valid and invalid input; contract tests against the OpenAPI spec.
- **Frontend:** manual walkthrough of the full journey on desktop and phone; component tests for the stats panel and chart on fixtures.
- **Performance target:** cached /trend responses under 2 seconds.

## 17. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Official resources arrive only on Nov 13 | Data-source-agnostic design; candidate datasets prepared now; catalog entry plus ETL run is all that is needed to add a variable |
| NASA servers slow or down during the event | Precomputed cache for every demo variable and region; live fetch is only a stretch feature |
| Earthdata login or download problems | Everyone sets up credentials in Phase 0; a shared pre-downloaded subset as backup |
| Statistics done wrong | Analysis in its own tested package; cross-library and Giovanni checks; one teammate reviews all stats code |
| Seasonality or autocorrelation produce false trends | Deseasonalize first; modified Mann-Kendall; cross-check with a second method; show warnings |
| Coarse data used for small regions | Minimum grid-cell rule with a clear message |
| Scope creep | MVP, Should, and Stretch tiers; feature freeze at hour 40 |
| Free-tier backend sleeps during the demo | Warm up before presenting; record a backup demo video |
| Teammates blocked on each other | Contract-first development and fixture-based mock server |
| Misleading claims about causes | Fixed caveat text; no causal language in explanations |

## 18. Demo and submission

**Demo script (about 3 minutes):**

1. State the problem: so many variables, trends differ by place, how do we know what is real?
2. Start the detective flow: pick water, Bangladesh, last 25 years.
3. Show the rainfall time series and trend line; read the verdict and slope per decade in plain language.
4. Show a second variable (temperature or vegetation) and one with no significant trend, to prove the tool is honest.
5. Compare two divisions with different trends.
6. Show the trend map, then the Methods page and data credits.
7. Close with how the same tool works for any region.

**Submission:** the official submission requirements and judging criteria were not available when this document was written. Before Phase 4, copy them into docs/submission.md and add any missing deliverables (project description, demo video, GitHub link, slides, and so on) to the plan. Also credit all NASA data sources in the app and the README, as open-data rules usually require.

## 19. Definition of done and open items

**MVP is done when:**

- A user can choose a variable and a region and see a time series with a trend line.
- The result shows slope per decade with a confidence interval, a p-value, a verdict, and a plain-language explanation.
- At least 4 variables and the Bangladesh divisions work from cache.
- The Methods page lists sources, methods, and limitations.
- The app is deployed and the demo runs smoothly on a phone and a laptop.

**Open items to settle:**

1. Final variable list after the Nov 13 resources.
2. Whether pre-event preparation is allowed and how (rules check).
3. Hosting choice and who owns the deployment.
4. Whether to include the optional LLM explainer.
5. Interface languages: English only, or English plus Bangla.
6. Submission requirements and deadline.
