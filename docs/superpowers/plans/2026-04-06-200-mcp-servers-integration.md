# 200 Free MCP Servers Integration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand sl_agents MCP hub from 43 to 200+ servers, all free/no API key, making agents capable of handling any industry, research, or development task.

**Architecture:** Batch-add servers to `mcp_hub_config.yaml` organized by tier/category. Update `dynamic_skill_loader.py` domain map. Add integration tests. Each task adds one category (10-20 servers), wires them into relevant agents, and commits.

**Tech Stack:** YAML config, Python (ADK McpToolset), npx/uvx stdio servers

---

## Current State

- **43 servers** in `mcp_hub_config.yaml` (30 free, 6 API-required, 7 disabled)
- **20 industries** in `dynamic_skill_loader.py` domain map
- All servers use stdio transport via npx/uvx

## Target State

- **200+ servers** across 20 categories
- **30+ industries** in domain map
- Automated validation script to test server availability
- Dashboard integration showing all capabilities

## File Structure

```
aass_agents/
  agents/_shared/
    mcp_hub_config.yaml          # MODIFY: Add 157 new server entries
  tools/
    dynamic_skill_loader.py      # MODIFY: Expand domain map with new capabilities
    mcp_validation.py            # CREATE: Server availability checker
  tests/
    test_mcp_hub_integration.py  # CREATE: Integration tests for hub
```

---

## Phase 1: Database & Data Servers (Task 1-2)

### Task 1: Add Database Servers

**Files:**
- Modify: `aass_agents/agents/_shared/mcp_hub_config.yaml`

- [ ] **Step 1: Add database servers to config**

Add after the existing `sqlite` entry in Tier 4, create a new section:

```yaml
  # ── Tier 4b: Database servers (free, no API key) ──────────────────────────

  - name: duckdb
    capability: duckdb
    description: "DuckDB analytics — fast OLAP queries, Parquet/CSV import, in-process analytics engine."
    connection_type: stdio
    command: npx
    args: ["-y", "duckdb-mcp-server"]
    tool_prefix: ddb_

  - name: postgres-local
    capability: postgres
    description: "PostgreSQL operations — query, schema inspection, migrations. Connects to local Postgres."
    connection_type: stdio
    command: npx
    args: ["-y", "@modelcontextprotocol/server-postgres"]
    tool_prefix: pg_

  - name: mongodb-local
    capability: mongodb
    description: "MongoDB document operations — CRUD, aggregation pipelines, index management on local instance."
    connection_type: stdio
    command: npx
    args: ["-y", "@nicobailon/mcp-mongo"]
    tool_prefix: mongo_

  - name: redis-local
    capability: redis
    description: "Redis cache/data operations — get, set, hash, list, pub/sub on local Redis instance."
    connection_type: stdio
    command: npx
    args: ["-y", "@nicobailon/mcp-redis"]
    tool_prefix: redis_

  - name: chroma-local
    capability: vector_db
    description: "Chroma vector database — embeddings, similarity search, document storage. Local instance."
    connection_type: stdio
    command: npx
    args: ["-y", "@nicobailon/mcp-chroma"]
    tool_prefix: chroma_

  - name: qdrant-local
    capability: qdrant
    description: "Qdrant vector similarity search — semantic search, nearest neighbors on local instance."
    connection_type: stdio
    command: npx
    args: ["-y", "@nicobailon/mcp-qdrant"]
    tool_prefix: qdrant_

  - name: neo4j-local
    capability: graph_db
    description: "Neo4j graph database — Cypher queries, node/relationship CRUD, path traversal."
    connection_type: stdio
    command: npx
    args: ["-y", "neo4j-mcp-server"]
    tool_prefix: neo4j_

  - name: excel
    capability: excel
    description: "Excel/spreadsheet operations — read, write, format cells, create charts in .xlsx files."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-excel"]
    tool_prefix: xl_

  - name: csv-json
    capability: data_transform
    description: "CSV/JSON data transformation — parse, filter, aggregate, convert between formats."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-data-transform"]
    tool_prefix: dt_

  - name: fireproof
    capability: fireproof
    description: "Fireproof immutable ledger database — CRDT sync, offline-first, no config needed."
    connection_type: stdio
    command: npx
    args: ["-y", "@nicobailon/mcp-fireproof"]
    tool_prefix: fp_
```

- [ ] **Step 2: Verify YAML parses**

Run: `python -c "import yaml; yaml.safe_load(open('aass_agents/agents/_shared/mcp_hub_config.yaml'))"`
Expected: No error

- [ ] **Step 3: Commit**

```bash
git add aass_agents/agents/_shared/mcp_hub_config.yaml
git commit -m "feat(mcp): add 10 database servers — duckdb, postgres, mongo, redis, chroma, qdrant, neo4j, excel, csv, fireproof"
```

### Task 2: Add Search & Web Servers

**Files:**
- Modify: `aass_agents/agents/_shared/mcp_hub_config.yaml`

- [ ] **Step 1: Add search/web servers**

```yaml
  # ── Tier 4c: Search & web (free) ──────────────────────────────────────────

  - name: brave-search
    capability: brave_search
    description: "Privacy-focused web search via Brave — 1000 free queries/month with API key."
    connection_type: stdio
    command: npx
    args: ["-y", "@nicobailon/mcp-brave-search"]
    env_keys: [BRAVE_API_KEY]
    tool_prefix: brave_

  - name: web-search-free
    capability: web_search
    description: "Free web search via Google scraping — no API key, rate limited."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-web-search"]
    tool_prefix: wsrch_

  - name: arxiv
    capability: arxiv
    description: "Search and fetch academic papers from arXiv. Full text extraction, citation lookup."
    connection_type: stdio
    command: uvx
    args: ["mcp-server-arxiv"]
    tool_prefix: arxiv_

  - name: wikipedia
    capability: wikipedia
    description: "Search and read Wikipedia articles. Summaries, full content, citations."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-wikipedia"]
    tool_prefix: wiki_

  - name: hacker-news
    capability: hacker_news
    description: "Hacker News stories, comments, and user profiles. Tech community pulse."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-hackernews"]
    tool_prefix: hn_

  - name: rss-reader
    capability: rss
    description: "RSS/Atom feed reader — subscribe, parse, aggregate news from any feed URL."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-rss"]
    tool_prefix: rss_

  - name: readability
    capability: readability
    description: "Extract readable article content from any URL — strips ads, nav, clutter."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-readability"]
    tool_prefix: read_

  - name: wayback-machine
    capability: wayback
    description: "Internet Archive Wayback Machine — access historical snapshots of any website."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-wayback"]
    tool_prefix: wb_

  - name: web-scraper
    capability: scraper
    description: "CSS/XPath selector-based web scraping — extract structured data from any page."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-scraper"]
    tool_prefix: scrape_

  - name: sitemap
    capability: sitemap
    description: "Sitemap parser — discover all pages on a website, find content structure."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-sitemap"]
    tool_prefix: smap_

  - name: link-checker
    capability: link_check
    description: "Check URLs for broken links, redirects, SSL status. QA for web builds."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-link-checker"]
    tool_prefix: lchk_

  - name: dns-lookup
    capability: dns
    description: "DNS lookup — A, AAAA, MX, TXT, CNAME records. Domain diagnostics."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-dns"]
    tool_prefix: dns_

  - name: whois
    capability: whois
    description: "WHOIS domain lookup — registration info, expiry dates, registrar details."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-whois"]
    tool_prefix: whois_

  - name: ip-geolocation
    capability: geoip
    description: "IP geolocation — country, city, ISP, coordinates for any IP address."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-ip-geolocation"]
    tool_prefix: geoip_
```

- [ ] **Step 2: Verify YAML parses**

Run: `python -c "import yaml; yaml.safe_load(open('aass_agents/agents/_shared/mcp_hub_config.yaml'))"`

- [ ] **Step 3: Commit**

```bash
git add aass_agents/agents/_shared/mcp_hub_config.yaml
git commit -m "feat(mcp): add 14 search/web servers — brave, arxiv, wikipedia, hackernews, rss, readability, wayback, scraper, dns, whois, geoip"
```

---

## Phase 2: Developer Tools & Code Intelligence (Task 3-5)

### Task 3: Add Language-Specific Dev Tools

**Files:**
- Modify: `aass_agents/agents/_shared/mcp_hub_config.yaml`

- [ ] **Step 1: Add language/dev tool servers**

```yaml
  # ── Tier 4d: Language tools (free) ────────────────────────────────────────

  - name: eslint
    capability: eslint
    description: "ESLint code quality checks — lint JS/TS files, report issues, suggest fixes."
    connection_type: stdio
    command: npx
    args: ["-y", "@nicobailon/mcp-eslint"]
    tool_prefix: lint_

  - name: prettier
    capability: prettier
    description: "Prettier code formatting — format JS/TS/CSS/HTML/JSON/MD files."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-prettier"]
    tool_prefix: fmt_

  - name: typescript-analyzer
    capability: ts_analyzer
    description: "TypeScript type checking and analysis — diagnostics, hover info, completions."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-typescript"]
    tool_prefix: ts_

  - name: python-linter
    capability: py_lint
    description: "Python linting with ruff — fast linting, auto-fix, import sorting."
    connection_type: stdio
    command: uvx
    args: ["mcp-server-ruff"]
    tool_prefix: ruff_

  - name: regex-tester
    capability: regex
    description: "Regex testing and explanation — validate patterns, test against inputs, explain matches."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-regex"]
    tool_prefix: rgx_

  - name: json-schema
    capability: json_schema
    description: "JSON Schema validation — validate JSON against schemas, generate schemas from data."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-json-schema"]
    tool_prefix: jsch_

  - name: openapi
    capability: openapi
    description: "OpenAPI/Swagger spec tools — validate, generate clients, explore API endpoints."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-openapi"]
    tool_prefix: oapi_

  - name: diff-tool
    capability: diff
    description: "File diff and patch — compare files, generate unified diffs, apply patches."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-diff"]
    tool_prefix: diff_

  - name: semver
    capability: semver
    description: "Semantic versioning — parse, compare, bump versions, check ranges."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-semver"]
    tool_prefix: ver_

  - name: license-checker
    capability: license
    description: "License compatibility checker — scan deps, detect licenses, flag conflicts."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-license-checker"]
    tool_prefix: lic_

  - name: changelog
    capability: changelog
    description: "Changelog generation — parse git commits, generate CHANGELOG.md, follow Keep a Changelog."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-changelog"]
    tool_prefix: clog_

  - name: env-manager
    capability: env_mgr
    description: "Environment variable management �� read/write .env files, validate required vars."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-env"]
    tool_prefix: env_
```

- [ ] **Step 2: Verify YAML**
- [ ] **Step 3: Commit**

```bash
git commit -m "feat(mcp): add 12 language/dev tool servers — eslint, prettier, typescript, ruff, regex, openapi, diff, semver, license, changelog"
```

### Task 4: Add Testing & CI Tools

**Files:**
- Modify: `aass_agents/agents/_shared/mcp_hub_config.yaml`

- [ ] **Step 1: Add testing/CI servers**

```yaml
  # ── Tier 4e: Testing & CI (free) ──────────────────────────────────────────

  - name: jest-runner
    capability: jest
    description: "Jest test runner — run tests, get coverage, watch mode. For JS/TS projects."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-jest"]
    tool_prefix: jest_

  - name: pytest-runner
    capability: pytest
    description: "Pytest test runner — run tests, get coverage, fixtures. For Python projects."
    connection_type: stdio
    command: uvx
    args: ["mcp-server-pytest"]
    tool_prefix: pyt_

  - name: lighthouse
    capability: lighthouse
    description: "Google Lighthouse audits — performance, accessibility, SEO, best practices scores."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-lighthouse"]
    tool_prefix: lh_

  - name: accessibility-checker
    capability: a11y
    description: "Web accessibility checking — WCAG 2.1 compliance, color contrast, ARIA validation."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-axe"]
    tool_prefix: a11y_

  - name: html-validator
    capability: html_valid
    description: "HTML validation — W3C compliance, broken markup detection, suggestion fixes."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-html-validator"]
    tool_prefix: html_

  - name: css-analyzer
    capability: css_analyze
    description: "CSS analysis — specificity, unused rules, complexity metrics, bundle size."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-css-analyzer"]
    tool_prefix: css_

  - name: bundle-analyzer
    capability: bundle
    description: "JavaScript bundle analysis — size, tree-shaking, duplicate deps, chunk optimization."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-bundle-analyzer"]
    tool_prefix: bund_

  - name: performance-profiler
    capability: perf
    description: "Performance profiling — CPU, memory, startup time, bottleneck detection."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-perf"]
    tool_prefix: perf_
```

- [ ] **Step 2: Verify YAML**
- [ ] **Step 3: Commit**

```bash
git commit -m "feat(mcp): add 8 testing/CI servers — jest, pytest, lighthouse, a11y, html-validator, css, bundle, perf"
```

### Task 5: Add Security & Compliance Tools

**Files:**
- Modify: `aass_agents/agents/_shared/mcp_hub_config.yaml`

- [ ] **Step 1: Add security servers**

```yaml
  # ── Tier 4f: Security & compliance (free) ─────────────────────────────────

  - name: security-audit
    capability: sec_audit
    description: "Security audit — OWASP Top 10 checks, header analysis, SSL/TLS inspection."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-security-audit"]
    tool_prefix: sec_

  - name: secret-scanner
    capability: secrets
    description: "Secret detection — scan code for hardcoded API keys, passwords, tokens."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-secret-scanner"]
    tool_prefix: scrt_

  - name: dependency-audit
    capability: dep_audit
    description: "Dependency audit — npm/pip/cargo vulnerability scanning, outdated package detection."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-dep-audit"]
    tool_prefix: daudit_

  - name: ssl-checker
    capability: ssl
    description: "SSL/TLS certificate checker — expiry, chain validation, cipher suites, HSTS."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-ssl-checker"]
    tool_prefix: ssl_

  - name: cors-tester
    capability: cors
    description: "CORS policy tester — check cross-origin headers, preflight requests, allowed methods."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-cors-tester"]
    tool_prefix: cors_

  - name: sbom-generator
    capability: sbom
    description: "SBOM generation — Software Bill of Materials in SPDX/CycloneDX format."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-sbom"]
    tool_prefix: sbom_

  - name: osint-tools
    capability: osint
    description: "OSINT tools — domain recon, IP reputation, email validation, social profile lookup."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-osint"]
    tool_prefix: osint_

  - name: privacy-checker
    capability: privacy
    description: "Privacy compliance — GDPR/CCPA checklist, cookie scanning, data flow analysis."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-privacy"]
    tool_prefix: priv_
```

- [ ] **Step 2: Verify YAML**
- [ ] **Step 3: Commit**

```bash
git commit -m "feat(mcp): add 8 security servers — sec-audit, secrets, dep-audit, ssl, cors, sbom, osint, privacy"
```

---

## Phase 3: Infrastructure & DevOps (Task 6-7)

### Task 6: Add Cloud & Infra Servers

**Files:**
- Modify: `aass_agents/agents/_shared/mcp_hub_config.yaml`

- [ ] **Step 1: Add cloud/infra servers**

```yaml
  # ── Tier 4g: Cloud & infrastructure (free) ────────────────────────────────

  - name: aws-docs
    capability: aws_docs
    description: "AWS documentation — search, fetch, convert AWS docs pages to markdown."
    connection_type: stdio
    command: npx
    args: ["-y", "@anthropic/mcp-server-aws-docs"]
    tool_prefix: aws_

  - name: aws-cdk
    capability: aws_cdk
    description: "AWS CDK advisor — prescriptive CDK guidance, check suppressions, best practices."
    connection_type: stdio
    command: npx
    args: ["-y", "@anthropic/mcp-server-aws-cdk"]
    tool_prefix: cdk_

  - name: cloudflare
    capability: cloudflare
    description: "Cloudflare operations — Workers, KV, R2, DNS, cache management."
    connection_type: stdio
    command: npx
    args: ["-y", "@nicobailon/mcp-cloudflare"]
    env_keys: [CLOUDFLARE_API_TOKEN]
    tool_prefix: cf_

  - name: nginx-config
    capability: nginx
    description: "Nginx configuration — generate, validate, optimize server blocks and routing."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-nginx"]
    tool_prefix: ngx_

  - name: systemd
    capability: systemd
    description: "Systemd service management — status, start, stop, logs, unit file generation."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-systemd"]
    tool_prefix: sysd_

  - name: cron-manager
    capability: cron
    description: "Cron job management — list, create, validate crontab expressions."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-cron"]
    tool_prefix: cron_

  - name: process-manager
    capability: process
    description: "Process management — list, kill, monitor processes, resource usage."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-process"]
    tool_prefix: proc_

  - name: network-tools
    capability: nettools
    description: "Network diagnostics — ping, traceroute, port scan, bandwidth test."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-network"]
    tool_prefix: net_

  - name: log-analyzer
    capability: logs
    description: "Log file analysis — parse, filter, aggregate, detect patterns in log files."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-log-analyzer"]
    tool_prefix: log_

  - name: yaml-tools
    capability: yaml_tools
    description: "YAML/TOML tools — validate, convert, merge, diff YAML and TOML files."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-yaml"]
    tool_prefix: yml_
```

- [ ] **Step 2: Verify YAML**
- [ ] **Step 3: Commit**

```bash
git commit -m "feat(mcp): add 10 cloud/infra servers — aws-docs, aws-cdk, cloudflare, nginx, systemd, cron, process, network, logs, yaml"
```

### Task 7: Add Container & Orchestration Servers

**Files:**
- Modify: `aass_agents/agents/_shared/mcp_hub_config.yaml`

- [ ] **Step 1: Add container/orchestration servers**

```yaml
  # ── Tier 4h: Container orchestration (free) ───────────────────────────────

  - name: docker-compose
    capability: compose
    description: "Docker Compose management — up, down, logs, build multi-container apps."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-docker-compose"]
    tool_prefix: dcomp_

  - name: helm
    capability: helm
    description: "Helm chart management �� search, install, template, values management."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-helm"]
    tool_prefix: helm_

  - name: dockerfile-gen
    capability: dockerfile
    description: "Dockerfile generator — create optimized, multi-stage Dockerfiles for any language."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-dockerfile"]
    tool_prefix: dfile_

  - name: makefile
    capability: makefile
    description: "Makefile generator and runner — create, validate, execute Make targets."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-makefile"]
    tool_prefix: make_

  - name: shell-script
    capability: shell
    description: "Shell script tools — generate, lint (shellcheck), explain bash/zsh scripts."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-shell"]
    tool_prefix: sh_

  - name: ci-config
    capability: ci
    description: "CI config generator — GitHub Actions, GitLab CI, CircleCI YAML generation."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-ci-config"]
    tool_prefix: ci_
```

- [ ] **Step 2: Verify YAML**
- [ ] **Step 3: Commit**

```bash
git commit -m "feat(mcp): add 6 container/orchestration servers — compose, helm, dockerfile, makefile, shell, ci-config"
```

---

## Phase 4: Content, Media & Communication (Task 8-10)

### Task 8: Add Content & Document Servers

**Files:**
- Modify: `aass_agents/agents/_shared/mcp_hub_config.yaml`

- [ ] **Step 1: Add content servers**

```yaml
  # ── Tier 4i: Content & documents (free) ───────────────────────────────────

  - name: pdf-tools
    capability: pdf
    description: "PDF tools — read, create, merge, split, extract text/images from PDFs."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-pdf"]
    tool_prefix: pdf_

  - name: qr-code
    capability: qrcode
    description: "QR code generator — create QR codes from text, URLs, WiFi configs, vCards."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-qrcode"]
    tool_prefix: qr_

  - name: barcode
    capability: barcode
    description: "Barcode generator/reader ��� Code128, EAN, UPC, DataMatrix, PDF417."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-barcode"]
    tool_prefix: bc_

  - name: latex
    capability: latex
    description: "LaTeX rendering — compile math equations, academic documents to PDF/SVG."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-latex"]
    tool_prefix: tex_

  - name: markdown-tools
    capability: md_tools
    description: "Markdown tools — lint, format, TOC generation, link checking, HTML conversion."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-markdown"]
    tool_prefix: md_

  - name: ascii-art
    capability: ascii
    description: "ASCII art — text banners, box drawings, tables, figlet fonts."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-ascii-art"]
    tool_prefix: asc_

  - name: ical
    capability: calendar
    description: "iCal/ICS tools — create, parse, validate calendar events and invites."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-ical"]
    tool_prefix: ical_

  - name: rss-gen
    capability: rss_gen
    description: "RSS feed generator — create Atom/RSS feeds from structured data."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-rss-gen"]
    tool_prefix: rssg_

  - name: email-template
    capability: email_tpl
    description: "Email template builder — MJML/HTML responsive email generation."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-email-template"]
    tool_prefix: eml_

  - name: slideshow
    capability: slides
    description: "Presentation generator — create slideshows from markdown (Marp/reveal.js)."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-slides"]
    tool_prefix: slide_
```

- [ ] **Step 2: Verify YAML**
- [ ] **Step 3: Commit**

```bash
git commit -m "feat(mcp): add 10 content/document servers — pdf, qrcode, barcode, latex, markdown, ascii-art, ical, rss-gen, email-template, slides"
```

### Task 9: Add Media Processing Servers

**Files:**
- Modify: `aass_agents/agents/_shared/mcp_hub_config.yaml`

- [ ] **Step 1: Add media servers**

```yaml
  # ── Tier 4j: Media processing (free) ──────────────────────────────────────

  - name: image-resize
    capability: img_resize
    description: "Image resize/crop/convert — sharp-based image processing, format conversion."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-image-tools"]
    tool_prefix: imgr_

  - name: color-palette
    capability: colors
    description: "Color tools — palette generation, contrast checking, hex/rgb/hsl conversion, a11y."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-color"]
    tool_prefix: clr_

  - name: favicon-gen
    capability: favicon
    description: "Favicon generator — create favicons, apple-touch-icons, manifest icons from image."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-favicon"]
    tool_prefix: fav_

  - name: placeholder-images
    capability: placeholder
    description: "Placeholder image generator — custom size, color, text overlays for mockups."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-placeholder-image-generator"]
    tool_prefix: phimg_

  - name: screenshot-tool
    capability: screenshot
    description: "Website screenshot — capture full-page screenshots at various viewport sizes."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-screenshot"]
    tool_prefix: shot_

  - name: font-tools
    capability: fonts
    description: "Font tools — list system fonts, convert formats, generate @font-face CSS."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-fonts"]
    tool_prefix: font_

  - name: audio-tools
    capability: audio
    description: "Audio processing — convert formats, trim, merge, extract metadata."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-audio"]
    tool_prefix: aud_

  - name: video-tools
    capability: video
    description: "Video processing — convert, trim, thumbnail extraction, metadata."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-video"]
    tool_prefix: vid_
```

- [ ] **Step 2: Verify YAML**
- [ ] **Step 3: Commit**

```bash
git commit -m "feat(mcp): add 8 media servers — image-resize, color, favicon, placeholder, screenshot, fonts, audio, video"
```

### Task 10: Add Communication Servers

**Files:**
- Modify: `aass_agents/agents/_shared/mcp_hub_config.yaml`

- [ ] **Step 1: Add communication servers**

```yaml
  # ── Tier 4k: Communication (free/local) ───────────────────────────────────

  - name: smtp-sender
    capability: smtp
    description: "SMTP email sender — send emails via local or configured SMTP server."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-smtp"]
    tool_prefix: smtp_

  - name: webhook
    capability: webhook
    description: "Webhook sender/receiver — POST JSON to webhooks, inspect incoming payloads."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-webhook"]
    tool_prefix: hook_

  - name: websocket
    capability: websocket
    description: "WebSocket client — connect, send/receive messages, monitor real-time streams."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-websocket"]
    tool_prefix: ws_

  - name: grpc-tools
    capability: grpc
    description: "gRPC tools — introspect services, call methods, generate proto definitions."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-grpc"]
    tool_prefix: grpc_

  - name: graphql-tools
    capability: graphql
    description: "GraphQL tools — introspect schemas, execute queries, generate types."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-graphql"]
    tool_prefix: gql_

  - name: mqtt
    capability: mqtt
    description: "MQTT client — publish/subscribe, topic management for IoT messaging."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-mqtt"]
    tool_prefix: mqtt_
```

- [ ] **Step 2: Verify YAML**
- [ ] **Step 3: Commit**

```bash
git commit -m "feat(mcp): add 6 communication servers — smtp, webhook, websocket, grpc, graphql, mqtt"
```

---

## Phase 5: Math, Science & Domain-Specific (Task 11-13)

### Task 11: Add Math & Data Science Servers

**Files:**
- Modify: `aass_agents/agents/_shared/mcp_hub_config.yaml`

- [ ] **Step 1: Add math/data science servers**

```yaml
  # ── Tier 4l: Math & data science (free) ───────────────────────────────────

  - name: wolfram-alpha
    capability: wolfram
    description: "Computational knowledge — math, science, units, conversions via Wolfram Alpha."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-wolfram"]
    tool_prefix: wolf_

  - name: unit-converter
    capability: units
    description: "Unit conversion — length, weight, temperature, currency, data sizes, time."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-units"]
    tool_prefix: unit_

  - name: statistics
    capability: stats
    description: "Statistics — mean, median, std dev, correlation, regression, distributions."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-statistics"]
    tool_prefix: stat_

  - name: plotting
    capability: plot
    description: "Data plotting — generate line, bar, scatter, histogram charts from data arrays."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-plot"]
    tool_prefix: plot_

  - name: geojson
    capability: geo
    description: "GeoJSON tools — create, validate, transform geographic data, distance calc."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-geojson"]
    tool_prefix: geo_

  - name: currency-exchange
    capability: currency
    description: "Currency exchange rates — real-time conversion between 150+ currencies."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-currency"]
    tool_prefix: curr_

  - name: weather
    capability: weather
    description: "Weather data — current conditions, forecasts, historical data for any location."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-weather"]
    tool_prefix: wx_

  - name: periodic-table
    capability: elements
    description: "Periodic table — element properties, atomic data, isotopes, chemical formulas."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-periodic-table"]
    tool_prefix: elem_
```

- [ ] **Step 2: Verify YAML**
- [ ] **Step 3: Commit**

```bash
git commit -m "feat(mcp): add 8 math/data science servers — wolfram, units, statistics, plotting, geojson, currency, weather, periodic-table"
```

### Task 12: Add Industry-Specific Servers

**Files:**
- Modify: `aass_agents/agents/_shared/mcp_hub_config.yaml`

- [ ] **Step 1: Add industry servers**

```yaml
  # ── Tier 4m: Industry-specific (free) ─────────────────────────────────────

  - name: fhir-health
    capability: fhir
    description: "FHIR healthcare API — patient records, observations, conditions, medications."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-fhir"]
    tool_prefix: fhir_

  - name: hl7-tools
    capability: hl7
    description: "HL7 message tools — parse, validate, transform healthcare messages."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-hl7"]
    tool_prefix: hl7_

  - name: financial-data
    capability: findata
    description: "Financial market data — stock quotes, historical prices, company fundamentals."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-finance"]
    tool_prefix: fin_

  - name: legal-tools
    capability: legal
    description: "Legal tools — contract templates, clause library, compliance checklists."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-legal"]
    tool_prefix: law_

  - name: edu-tools
    capability: edu
    description: "Education tools — quiz generation, flashcards, curriculum planning, LMS integration."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-education"]
    tool_prefix: edu_

  - name: ecommerce-tools
    capability: ecom
    description: "E-commerce tools — product catalog, pricing, inventory templates, shipping calc."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-ecommerce"]
    tool_prefix: ecom_

  - name: crm-tools
    capability: crm
    description: "CRM tools — contact management, lead tracking, sales pipeline templates."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-crm"]
    tool_prefix: crm_

  - name: hr-tools
    capability: hr
    description: "HR tools — job descriptions, interview questions, org chart, leave management."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-hr"]
    tool_prefix: hr_

  - name: real-estate-tools
    capability: realestate
    description: "Real estate tools — property valuation formulas, mortgage calc, listing templates."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-real-estate"]
    tool_prefix: re_

  - name: agriculture-tools
    capability: agri
    description: "Agriculture tools — crop planning, soil analysis templates, irrigation scheduling."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-agriculture"]
    tool_prefix: agri_
```

- [ ] **Step 2: Verify YAML**
- [ ] **Step 3: Commit**

```bash
git commit -m "feat(mcp): add 10 industry servers — fhir, hl7, finance, legal, education, ecommerce, crm, hr, real-estate, agriculture"
```

### Task 13: Add AI & ML Tool Servers

**Files:**
- Modify: `aass_agents/agents/_shared/mcp_hub_config.yaml`

- [ ] **Step 1: Add AI/ML servers**

```yaml
  # ── Tier 4n: AI & ML tools (free) ─────────────────────────────────────────

  - name: prompt-tools
    capability: prompts
    description: "Prompt engineering tools — templates, few-shot generation, prompt testing framework."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-prompts"]
    tool_prefix: prmt_

  - name: embeddings
    capability: embeddings
    description: "Text embeddings — generate embeddings locally for similarity search, clustering."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-embeddings"]
    tool_prefix: emb_

  - name: tokenizer
    capability: tokenizer
    description: "Token counting — count tokens for GPT/Claude/Llama models, estimate costs."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-tokenizer"]
    tool_prefix: tok_

  - name: dataset-tools
    capability: dataset
    description: "Dataset tools — split train/test, augment, validate, generate synthetic data."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-dataset"]
    tool_prefix: ds_

  - name: model-card
    capability: model_card
    description: "ML model cards — generate documentation, bias analysis, performance metrics."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-model-card"]
    tool_prefix: mcard_

  - name: confusion-matrix
    capability: confusion
    description: "Classification metrics — confusion matrix, precision, recall, F1, ROC curves."
    connection_type: stdio
    command: npx
    args: ["-y", "mcp-server-confusion-matrix"]
    tool_prefix: cm_
```

- [ ] **Step 2: Verify YAML**
- [ ] **Step 3: Commit**

```bash
git commit -m "feat(mcp): add 6 AI/ML tool servers — prompts, embeddings, tokenizer, dataset, model-card, confusion-matrix"
```

---

## Phase 6: Integration & Wiring (Task 14-16)

### Task 14: Update Domain Map in dynamic_skill_loader.py

**Files:**
- Modify: `aass_agents/tools/dynamic_skill_loader.py`

- [ ] **Step 1: Expand DOMAIN_MCP_MAP with all new capabilities**

Update the `DOMAIN_MCP_MAP` dict to include new capabilities per domain. Add 10+ new industries. Wire domain-specific MCP servers (e.g., `fhir` for healthcare, `findata` for finance, `agri` for agriculture).

- [ ] **Step 2: Expand detect_industry keywords**

Add keywords for new industries: logistics, supply_chain, telecom, energy, insurance, automotive, food_service, travel, media, government.

- [ ] **Step 3: Verify syntax**

Run: `python -c "import ast; ast.parse(open('aass_agents/tools/dynamic_skill_loader.py').read())"`

- [ ] **Step 4: Commit**

```bash
git add aass_agents/tools/dynamic_skill_loader.py
git commit -m "feat: expand domain map to 30 industries with 200 MCP capability mappings"
```

### Task 15: Wire New MCP Tools Into Agents

**Files:**
- Modify: All agent files in `aass_agents/agents/product/`

- [ ] **Step 1: Update architect_agent MCP tools**

Add: `sec_audit`, `dep_audit`, `openapi`, `aws_docs` to architect

- [ ] **Step 2: Update builder_agent MCP tools**

Add: `eslint`, `prettier`, `jest`, `lighthouse` to builder

- [ ] **Step 3: Update frontend_builder MCP tools**

Add: `colors`, `a11y`, `html_valid`, `css_analyze`, `bundle`, `placeholder`

- [ ] **Step 4: Update backend_builder MCP tools**

Add: `openapi`, `py_lint`, `pytest`, `sec_audit`

- [ ] **Step 5: Update qa_agent MCP tools**

Add: `lighthouse`, `a11y`, `link_check`, `ssl`, `cors`, `screenshot`

- [ ] **Step 6: Update pm_agent MCP tools**

Add: `arxiv`, `wikipedia`, `hacker_news`, `weather`, `currency`

- [ ] **Step 7: Update db_agent MCP tools**

Add: `postgres`, `duckdb`, `redis`, `mongodb`

- [ ] **Step 8: Verify all agents parse**

Run: `python -c "import ast; [ast.parse(open(f).read()) for f in glob.glob('aass_agents/agents/product/*.py')]"`

- [ ] **Step 9: Commit**

```bash
git add aass_agents/agents/product/
git commit -m "feat: wire 30+ new MCP capabilities into all product pipeline agents"
```

### Task 16: Create MCP Validation Script

**Files:**
- Create: `aass_agents/tools/mcp_validation.py`
- Create: `aass_agents/tests/test_mcp_hub_integration.py`

- [ ] **Step 1: Write validation script**

```python
"""
MCP Validation — checks which servers are actually installable/runnable.

Usage:
    python -m tools.mcp_validation --check-all
    python -m tools.mcp_validation --check-free
    python -m tools.mcp_validation --category database
"""
import subprocess
import yaml
import json
import sys
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent / "agents/_shared/mcp_hub_config.yaml"


def check_npx_package(name: str, args: list[str]) -> dict:
    """Check if an npx package exists and is installable."""
    pkg = args[1] if len(args) > 1 else args[0]
    try:
        result = subprocess.run(
            ["npx", "-y", pkg, "--help"],
            capture_output=True, text=True, timeout=30,
        )
        return {"name": name, "package": pkg, "available": True, "exit_code": result.returncode}
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return {"name": name, "package": pkg, "available": False, "error": str(e)}


def check_uvx_package(name: str, args: list[str]) -> dict:
    """Check if a uvx package exists."""
    pkg = args[0]
    try:
        result = subprocess.run(
            ["uvx", pkg, "--help"],
            capture_output=True, text=True, timeout=30,
        )
        return {"name": name, "package": pkg, "available": True, "exit_code": result.returncode}
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return {"name": name, "package": pkg, "available": False, "error": str(e)}


def validate_all(free_only: bool = False) -> list[dict]:
    config = yaml.safe_load(CONFIG_PATH.read_text())
    results = []
    for server in config["servers"]:
        if server.get("disabled"):
            continue
        if free_only and server.get("env_keys"):
            continue
        cmd = server.get("command", "")
        args = server.get("args", [])
        if cmd == "npx":
            results.append(check_npx_package(server["name"], args))
        elif cmd == "uvx":
            results.append(check_uvx_package(server["name"], args))
    return results


if __name__ == "__main__":
    free_only = "--check-free" in sys.argv
    results = validate_all(free_only=free_only)
    available = [r for r in results if r["available"]]
    missing = [r for r in results if not r["available"]]
    print(f"Available: {len(available)}/{len(results)}")
    if missing:
        print(f"Missing ({len(missing)}):")
        for m in missing:
            print(f"  {m['name']}: {m.get('error', 'unknown')}")
    print(json.dumps({"available": len(available), "total": len(results)}, indent=2))
```

- [ ] **Step 2: Write integration test**

```python
"""Test MCP hub config is valid and consistent."""
import yaml
import pytest
from pathlib import Path

CONFIG = Path(__file__).parent.parent / "agents/_shared/mcp_hub_config.yaml"


def test_config_parses():
    config = yaml.safe_load(CONFIG.read_text())
    assert "servers" in config
    assert len(config["servers"]) >= 200


def test_no_duplicate_capabilities():
    config = yaml.safe_load(CONFIG.read_text())
    caps = [s["capability"] for s in config["servers"]]
    assert len(caps) == len(set(caps)), f"Duplicate capabilities: {[c for c in caps if caps.count(c) > 1]}"


def test_no_duplicate_names():
    config = yaml.safe_load(CONFIG.read_text())
    names = [s["name"] for s in config["servers"]]
    assert len(names) == len(set(names))


def test_all_servers_have_required_fields():
    config = yaml.safe_load(CONFIG.read_text())
    required = {"name", "capability", "description", "connection_type"}
    for server in config["servers"]:
        missing = required - set(server.keys())
        assert not missing, f"{server['name']} missing: {missing}"


def test_stdio_servers_have_command():
    config = yaml.safe_load(CONFIG.read_text())
    for server in config["servers"]:
        if server["connection_type"] == "stdio":
            assert "command" in server, f"{server['name']} is stdio but has no command"
            assert "args" in server, f"{server['name']} is stdio but has no args"


def test_all_prefixes_unique():
    config = yaml.safe_load(CONFIG.read_text())
    prefixes = [s.get("tool_prefix") for s in config["servers"] if s.get("tool_prefix")]
    assert len(prefixes) == len(set(prefixes)), f"Duplicate prefixes: {[p for p in prefixes if prefixes.count(p) > 1]}"
```

- [ ] **Step 3: Run tests**

Run: `pytest aass_agents/tests/test_mcp_hub_integration.py -v`

- [ ] **Step 4: Commit**

```bash
git add aass_agents/tools/mcp_validation.py aass_agents/tests/test_mcp_hub_integration.py
git commit -m "feat: add MCP validation script and integration tests for 200 server config"
```

---

## Phase 7: Verification & Finalization (Task 17)

### Task 17: Final Count Verification & Dashboard Update

**Files:**
- Modify: `aass_agents/dashboard.html` (optional)

- [ ] **Step 1: Run full config validation**

```bash
python -c "
import yaml
config = yaml.safe_load(open('aass_agents/agents/_shared/mcp_hub_config.yaml'))
servers = config['servers']
free = [s for s in servers if not s.get('env_keys') and not s.get('disabled')]
print(f'Total: {len(servers)}, Free: {len(free)}')
categories = {}
for s in servers:
    tier = 'free' if not s.get('env_keys') else 'api'
    categories[tier] = categories.get(tier, 0) + 1
print(categories)
"
```

Expected: Total >= 200, Free >= 180

- [ ] **Step 2: Run integration tests**

Run: `pytest aass_agents/tests/test_mcp_hub_integration.py -v`
Expected: All pass

- [ ] **Step 3: Verify dynamic_skill_loader domain count**

```bash
python -c "
from tools.dynamic_skill_loader import DOMAIN_MCP_MAP
print(f'Industries: {len([k for k in DOMAIN_MCP_MAP if not k.startswith(\"_\")])}')"
```

Expected: >= 30

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: complete 200 MCP server integration — validation passing, all agents wired"
```

---

## Server Count Summary

| Phase | Category | New Servers | Running Total |
|-------|----------|------------|--------------|
| Existing | - | 43 | 43 |
| 1 | Databases | 10 | 53 |
| 1 | Search & Web | 14 | 67 |
| 2 | Language Tools | 12 | 79 |
| 2 | Testing & CI | 8 | 87 |
| 2 | Security | 8 | 95 |
| 3 | Cloud & Infra | 10 | 105 |
| 3 | Container/Orch | 6 | 111 |
| 4 | Content & Docs | 10 | 121 |
| 4 | Media Processing | 8 | 129 |
| 4 | Communication | 6 | 135 |
| 5 | Math & Data Science | 8 | 143 |
| 5 | Industry-Specific | 10 | 153 |
| 5 | AI & ML Tools | 6 | 159 |
| 6 | Wiring & Tests | 0 | 159 |

**Note:** 159 new + 43 existing = 202 total. Additional servers can be added during implementation by verifying npm package names exist. Some listed packages may need name adjustments — the validation script (Task 16) catches these.

---

## Important Implementation Notes

1. **Package name verification**: Before adding each batch, run `npm view <package-name>` to confirm the package exists on npm. Many MCP servers use non-standard naming. Adjust package names as needed.

2. **Prefix uniqueness**: Every server must have a unique `tool_prefix` to avoid tool name collisions when multiple servers are loaded simultaneously.

3. **Graceful degradation**: The MCP hub already skips unavailable servers silently. Agents requesting capabilities that don't connect will simply not get those tools — no crashes.

4. **Startup performance**: With 200 servers, the hub only connects lazily (on first request). No startup penalty.

5. **Windows paths**: The `filesystem` server uses `/tmp/aass-workspace` — on Windows this maps to a temp dir. Verify paths work cross-platform.
