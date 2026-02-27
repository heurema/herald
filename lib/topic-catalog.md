# Built-in Topic Catalog

Match user input to topics below. Fuzzy matching: "k8s"→devops, "js"→typescript, "py"→python.

## rust
aliases: rustlang
keywords: ["rust", "cargo", "rust lang", "crate", "tokio", "memory safety", "ferris"]
feeds:
  - name: "This Week in Rust"
    url: "https://this-week-in-rust.org/rss.xml"
    tier: 2
    weight: 0.25
  - name: "r/rust"
    url: "https://www.reddit.com/r/rust.rss"
    tier: 3
    weight: 0.15
  - name: "Rust Blog"
    url: "https://blog.rust-lang.org/feed.xml"
    tier: 1
    weight: 0.30

## devops
aliases: kubernetes, k8s, infra, platform engineering
keywords: ["kubernetes", "docker", "terraform", "ansible", "ci/cd", "helm", "gitops", "observability", "service mesh", "platform engineering"]
feeds:
  - name: "The New Stack"
    url: "https://thenewstack.io/feed/"
    tier: 1
    weight: 0.20
  - name: "Kubernetes Blog"
    url: "https://kubernetes.io/feed.xml"
    tier: 1
    weight: 0.30
  - name: "r/devops"
    url: "https://www.reddit.com/r/devops.rss"
    tier: 3
    weight: 0.15
  - name: "CNCF Blog"
    url: "https://www.cncf.io/feed/"
    tier: 2
    weight: 0.20

## golang
aliases: go
keywords: ["golang", "go lang", "goroutine", "gopher", "go module"]
feeds:
  - name: "Go Blog"
    url: "https://go.dev/blog/feed.atom"
    tier: 1
    weight: 0.30
  - name: "r/golang"
    url: "https://www.reddit.com/r/golang.rss"
    tier: 3
    weight: 0.15

## typescript
aliases: javascript, js, ts, webdev, frontend
keywords: ["typescript", "javascript", "react", "nextjs", "vite", "web performance", "node.js", "deno", "bun"]
feeds:
  - name: "JavaScript Weekly"
    url: "https://cprss.s3.amazonaws.com/javascriptweekly.com.xml"
    tier: 2
    weight: 0.25
  - name: "Dev.to JavaScript"
    url: "https://dev.to/feed/tag/javascript"
    tier: 3
    weight: 0.15

## security
aliases: infosec, cybersecurity, appsec
keywords: ["security", "vulnerability", "cve", "infosec", "zero-day", "supply chain attack", "ransomware"]
feeds:
  - name: "Krebs on Security"
    url: "https://krebsonsecurity.com/feed/"
    tier: 1
    weight: 0.30
  - name: "Schneier on Security"
    url: "https://www.schneier.com/feed/atom/"
    tier: 1
    weight: 0.25
  - name: "r/netsec"
    url: "https://www.reddit.com/r/netsec.rss"
    tier: 3
    weight: 0.15

## python
aliases: py, django, fastapi
keywords: ["python", "django", "fastapi", "pandas", "numpy", "pytorch", "flask"]
feeds:
  - name: "Python Weekly"
    url: "https://us2.campaign-archive.com/feed?u=e2e180baf855ac797ef407fc7&id=9e26887fc5"
    tier: 2
    weight: 0.25
  - name: "r/Python"
    url: "https://www.reddit.com/r/Python.rss"
    tier: 3
    weight: 0.15
  - name: "Real Python"
    url: "https://realpython.com/atom.xml"
    tier: 2
    weight: 0.20

## data
aliases: data science, ml, machine learning, data engineering
keywords: ["data science", "machine learning", "data pipeline", "spark", "dbt", "snowflake", "data lakehouse", "feature store"]
feeds:
  - name: "r/datascience"
    url: "https://www.reddit.com/r/datascience.rss"
    tier: 3
    weight: 0.15
  - name: "r/dataengineering"
    url: "https://www.reddit.com/r/dataengineering.rss"
    tier: 3
    weight: 0.15
