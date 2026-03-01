# AI Code Review Tools — Research

CONTEXT: Greptile ($30/dev/mo) is being dropped due to cost; need a replacement that reviews GitHub PRs with repo-wide context.
DATE: 2026-02-27

## Question

Which AI-powered code review tools can replace Greptile for GitHub PR review — free or significantly cheaper — while maintaining repo-wide context understanding and the ability to catch bugs, security issues, and logic errors, triggered from CLI or CI/CD?

## Evidence

### Baseline: Greptile (current tool being replaced)

- **Pricing:** $30/developer/month flat rate, unlimited reviews. Up to 20% off for annual contracts. ([Greptile Pricing](https://www.greptile.com/pricing))
- **What it does:** Indexes the full codebase and reviews PRs with that context. Known for deep repo-wide awareness.
- **Why dropping:** At $30/dev/mo for a small team, cost is disproportionate.

---

### 1. CodeRabbit

**Source:** [coderabbit.ai/pricing](https://www.coderabbit.ai/pricing), [CodeRabbit blog on context](https://www.coderabbit.ai/blog/how-coderabbit-delivers-accurate-ai-code-reviews-on-massive-codebases)

- **Pricing:**
  - Free: $0 (unlimited public repos, PR summarization only, no full review)
  - Pro: $24/dev/mo (annual) or $30/dev/mo (monthly) — unlimited private repo reviews
  - Enterprise: custom (self-hosting, SLA, RBAC)
  - 14-day free trial, no credit card required
- **Repo context:** Strong. Uses Codegraph (lightweight map of definitions/references), semantic indexing (embeddings of functions, classes, modules, prior PRs), LanceDB for vector search at scale, and commits history analysis. Pulls "dozens of points of context" beyond the diff. Cross-file issue detection is a documented capability.
- **Triggering:** Installs as a GitHub App; auto-reviews on PR open/update. Also has IDE plugin (VS Code). CLI not natively supported.
- **Quality:** 40+ linters and SAST tools synthesized into human-readable feedback. Real-time web query for documentation context (new in 2026). Code graph analysis for dependency understanding.
- **Limitations:** Cannot reason about cross-repo dependencies or historical architectural decisions made outside git. Review is tied to what can be indexed from the repository.
- **Verdict:** Best-in-class commercial option. At $24/dev/mo it is marginally cheaper than Greptile but not dramatically so. The free tier only gives summaries, not real reviews. Most relevant for teams wanting zero configuration.

---

### 2. GitHub Copilot Code Review

**Source:** [GitHub Copilot plans](https://github.com/features/copilot/plans), [GitHub Changelog Oct 2025](https://github.blog/changelog/2025-10-28-new-public-preview-features-in-copilot-code-review-ai-reviews-that-see-the-full-picture/), [Copilot code review GA](https://github.blog/changelog/2025-04-04-copilot-code-review-now-generally-available/)

- **Pricing:**
  - Free tier: $0 — code review NOT included
  - Pro: $10/user/mo — code review included (limited premium requests)
  - Pro+: $39/user/mo — higher premium request quota
  - Business: $19/user/mo — code review included (opt-in, preview)
  - Enterprise: $39/user/mo
  - Metered overflow: $0.04/premium request beyond monthly allocation (since June 2025)
- **Repo context:** Full context gathering as of October 2025 public preview. Uses agentic tool calling to read source files, explore directory structure, run CodeQL and ESLint. Copilot Memory (Pro/Pro+ only) stores learned repository patterns across reviews. Business/Enterprise users must opt in to preview features.
- **Triggering:** Assign Copilot as a reviewer directly in GitHub UI. Runs via GitHub Actions infrastructure (requires GitHub-hosted runners; organizations with runners disabled fall back to limited mode).
- **Quality:** Inline comments with suggested fixes. CodeQL + ESLint integration for security scanning. Deterministic detections (public preview) for pattern-based issues.
- **Limitations:** Metered billing adds unpredictability for high-PR-volume teams. Context gathering features are still in public preview for Business/Enterprise. Not triggerable from external CLI without GitHub API workarounds.
- **Verdict:** Excellent value if the team already pays for Copilot Pro ($10/mo). If Copilot is already in use, code review comes at zero additional cost. The strongest cost argument: zero marginal cost for existing Copilot subscribers.

---

### 3. Sourcery

**Source:** [sourcery.ai](https://www.sourcery.ai/), [Sourcery review 2025](https://skywork.ai/skypage/en/Sourcery-AI-In-Depth-Review-(2025)-My-Experience-with-the-AI-Code-Reviewer/1975259544421462016), [devtoolsacademy 2025 state](https://www.devtoolsacademy.com/blog/state-of-ai-code-review-tools-2025/)

- **Pricing:**
  - Free: public repos, unlimited; private repos 14-day trial
  - Pro: $12/seat/mo
  - Enterprise: custom (self-hosting option available)
- **Repo context:** Limited. Deep refactoring analysis focused on Python, JavaScript, TypeScript. General review is language-agnostic (30+ languages) but lacks codebase-wide semantic indexing comparable to CodeRabbit or Greptile. Reviews the diff with surrounding context, not a full indexed graph.
- **Triggering:** GitHub/GitLab app (auto-reviews PRs), IDE plugins (VS Code, PyCharm). CLI not a primary interface.
- **Quality:** Refactoring suggestions, bug detection, security issues, code smells. Auto-generates PR summaries and change diagrams. Learns from developer feedback (dismissals) over time.
- **Limitations:** Best value for Python-heavy codebases. Weak on full-repo architectural context. Not ideal for polyglot teams expecting deep cross-file analysis.
- **Verdict:** Cheapest commercial option at $12/seat/mo. Good for Python teams. Insufficient repo-wide context for complex, multi-language codebases.

---

### 4. Qodana (JetBrains)

**Source:** [jetbrains.com/qodana](https://www.jetbrains.com/qodana/), [Qodana pricing](https://www.jetbrains.com/help/qodana/pricing.html), [Qodana buy](https://www.jetbrains.com/qodana/buy/)

- **Pricing:**
  - Community: free (limited inspections, open source only)
  - Ultimate: $6/active contributor/mo (minimum 3 contributors)
  - Ultimate Plus: ~€90/contributor/mo — includes taint analysis, license audit
  - 60-day free trial for paid tiers
  - "Active contributor" = anyone who committed in the last 90 days
- **Repo context:** Full static analysis of the entire codebase (not just diff). 3,000+ inspection rules, same engines as IntelliJ IDEA / PyCharm / WebStorm. 60+ languages. Taint analysis traces data flows across the application. Historical trend tracking.
- **Triggering:** Native CI/CD integration (GitHub Actions, GitLab CI, Jenkins, TeamCity). CLI tool available (`qodana scan`). This is a first-class use case.
- **Quality:** SAST platform, not an LLM reviewer. Catches class-level issues: security vulnerabilities, taint flows, license violations, performance patterns. Does not generate natural language suggestions in the same conversational style as LLM-based tools.
- **Limitations:** Primarily static analysis — not AI in the LLM sense. Will not understand intent or catch logic errors that pass static checks. No PR-level conversational review. Better as a complement than a Greptile replacement.
- **Verdict:** Strong for deterministic security and quality gates ($6/contributor/mo Ultimate is very cheap). Not a direct Greptile replacement — different category. Best used alongside an LLM reviewer.

---

### 5. Ellipsis

**Source:** [ellipsis.dev](https://www.ellipsis.dev/), [Ellipsis docs](https://docs.ellipsis.dev/features/code-review), [SourceForge reviews 2025](https://sourceforge.net/software/product/Ellipsis.dev/)

- **Pricing:**
  - $20/user/mo, seat-based, unlimited usage
  - 7-day free trial
- **Repo context:** Reviews every PR with AI-generated summaries and per-commit feedback. Documentation does not explicitly describe full codebase indexing equivalent to Greptile. Context appears diff-plus-surrounding-files, not full graph traversal.
- **Triggering:** GitHub app (auto-reviews on every commit/PR within ~2 minutes). No documented CLI trigger.
- **Quality:** PR summaries, per-commit reviews, code generation, Q&A on code. Fast turnaround (~2 minutes). Focuses on bugs, security, style.
- **Limitations:** Less established than CodeRabbit or Qodo Merge. No CLI trigger. Repo context depth unclear from public documentation. YC-backed but smaller community.
- **Verdict:** Competitive on price vs Greptile ($20 vs $30/mo). Reasonable option if Qodo Merge or Copilot don't fit. Needs hands-on evaluation for context quality.

---

### 6. PR-Agent / Qodo Merge (formerly CodiumAI)

**Source:** [github.com/qodo-ai/pr-agent](https://github.com/qodo-ai/pr-agent), [qodo-merge-docs.qodo.ai](https://qodo-merge-docs.qodo.ai/), [qodo.ai/pricing](https://www.qodo.ai/pricing/)

- **Pricing:**
  - Open source (self-hosted): free — bring your own API key (OpenAI, Claude, Gemini, local models)
  - Qodo Merge free tier: 30 PR reviews/org/mo (limited-time, normally 75 credits)
  - Teams: $30/user/mo (currently discounted from $38; normally 20 PRs/user/mo unlimited during promo)
  - Enterprise: custom (multi-repo context engine, SSO, on-prem)
- **Repo context:** The open source version uses compression strategies and dynamic context within the diff window. The Enterprise tier adds a "context engine for multi-repo awareness." The free/Teams tiers do not include full codebase indexing — context is limited to the PR diff and fetched ticket context.
- **Triggering:** Multiple modes — CLI (`python -m pr_agent.cli`), GitHub Actions, GitHub App webhook, comment bot (`/review`, `/improve` in PR comments). Excellent CI/CD integration. Most flexible triggering of all reviewed tools.
- **Quality:** 10 tools: Review, Improve, Describe, Ask, Add Docs, Generate Labels, Similar Issues, Help, Update Changelog, Compliance (new 2025 — security + ticket requirement checks). GPT-5 support added. Confidence-based filtering reduces noise.
- **Limitations:** Free and Teams tiers lack full repo indexing (Enterprise only). Self-hosted requires managing API keys and infra. The 30 PR/mo free org limit is quickly exhausted on active repos.
- **Verdict:** Best open source option. Self-hosted with Claude API key has near-zero platform cost (pay only API tokens). Teams tier at $30/user/mo matches Greptile's price — not a savings. The sweet spot is self-hosted on Claude Sonnet 4 API.

---

### 7. Claude Code Native: `/code-review` Plugin

**Source:** [claude.com/plugins/code-review](https://claude.com/plugins/code-review), [github.com/anthropics/claude-code plugin README](https://github.com/anthropics/claude-code/blob/main/plugins/code-review/README.md)

- **Pricing:** Included in Claude Code subscription. 100,000+ installs. Anthropic Verified. No additional cost beyond existing Claude Max/Team subscription.
- **Repo context:** Full. Claude Code already has access to the entire checked-out repo via file tools. The plugin runs inside Claude Code's context which can read any file, run git commands, and inspect history. Not limited to the diff — can traverse the full codebase.
- **Triggering:** CLI command `/code-review` or `/code-review --comment` (posts to GitHub). Runs on the current PR branch in the terminal. Can be wrapped in a shell script or CI/CD step that invokes `claude` with the plugin command.
- **Quality:** 5 parallel agents (CLAUDE.md compliance x2, bug detection, git history analysis, prior PR comment review). Confidence scoring (0-100, default threshold 80). Filters closed/draft/automated/already-reviewed PRs. Posts findings with full SHA and line range links.
- **Limitations:** Requires Claude Code session to be running (not a standalone webhook bot). For fully automated CI/CD use, needs `claude-code-action` GitHub Action wrapper. Does not install as a persistent GitHub bot — must be invoked per review.
- **Verdict:** Zero marginal cost for existing Claude Code subscribers. Full repo context is native. The primary limitation is invocation model (pull, not push) — requires a trigger step in CI rather than being a passive bot. Highly recommended as primary or fallback reviewer.

---

### 8. DIY: claude-code-action + claude-code-security-review

**Source:** [github.com/anthropics/claude-code-action](https://github.com/anthropics/claude-code-action), [github.com/anthropics/claude-code-security-review](https://github.com/anthropics/claude-code-security-review), [GitHub Marketplace: Claude PR Reviewer](https://github.com/marketplace/actions/claude-pr-reviewer)

- **Pricing:** API cost only. Claude Sonnet 4.6: $3/M input tokens + $15/M output tokens. A typical PR review (10-50 files, 500-3000 lines of context) costs approximately $0.05–$0.50 per review. For 100 PRs/month: ~$5–$50/mo. Prompt caching reduces re-read costs by up to 90%. Batch API adds 50% discount for async processing.
- **Repo context:** Configurable. `claude-code-action` can be given explicit prompts to read specific files, run grep, explore directory structure. `claude-code-security-review` scans changed files (diff-aware) by default. Full repo context requires explicit prompt engineering.
- **Triggering:** GitHub Actions — `pull_request` trigger (on open/synchronize), comment trigger (`@claude` mention), or scheduled. Full CI/CD native. YAML workflow file, one-time setup.
- **Quality:**
  - `claude-code-action`: General review with customizable prompt. Can enforce CLAUDE.md rules, check tests, review security. Inline PR comments.
  - `claude-code-security-review`: Security-specialized. Detects injection, auth flaws, hardcoded secrets, XSS, cryptographic issues, business logic flaws. Uses `claude-opus-4-1` by default (configurable). Language agnostic.
  - `claude-pr-reviewer` (marketplace): Uses `pr-review-toolkit` plugin. Reviews code quality, test coverage, error handling, type design. `@claude` interactive mentions in PR.
- **Limitations:** `claude-code-security-review` is not hardened against prompt injection — should only run on trusted PRs (not external contributor forks without approval gate). Full repo context requires manual prompt configuration. Requires ANTHROPIC_API_KEY in GitHub Secrets.
- **Verdict:** Lowest possible cost at scale. Maximum flexibility. Requires one-time setup effort (~2-4 hours). Ideal for teams already on Claude API or Claude Code subscription. The security review action alone covers the most critical use case (vulnerability detection) at near-zero cost.

---

### Comparative Summary

| Tool | Price/dev/mo | Repo Context | CLI/CI Trigger | Key Strength | Key Weakness |
|------|-------------|--------------|----------------|--------------|--------------|
| **Greptile** (baseline) | $30 | Full index | CI/webhook | Deep context | Cost |
| **CodeRabbit** | $24 (Pro) | Full (Codegraph) | GitHub App | Best commercial quality | Similar cost to Greptile |
| **GitHub Copilot Review** | $0 if on $10 Pro | Full (agentic, preview) | GitHub UI/Actions | Free with Copilot | Preview features; metered overflow |
| **Sourcery** | $12 | Diff + surrounding | GitHub App | Cheapest commercial | Weak cross-file context |
| **Qodana** | $6 (Ultimate) | Full SAST | CLI + CI | Deterministic security | Not LLM; no conversational review |
| **Ellipsis** | $20 | Diff-level (unclear) | GitHub App | Fast, simple | Smaller ecosystem |
| **Qodo Merge** (self-hosted) | ~$5–15 API only | Diff (Enterprise: full) | CLI + CI + GitHub App | Open source, flexible | Infra management needed |
| **Claude Code `/code-review`** | $0 (in subscription) | Full (native) | CLI + CI (Action) | Zero cost, full context | Not a passive bot |
| **DIY claude-code-action** | $5–50 API (100 PRs) | Configurable | GitHub Actions native | Maximum flexibility, cheapest | Setup effort, prompt engineering |

## Analysis

**Cost vs Greptile ($30/dev/mo):**
The only tools that are genuinely cheaper at scale are: Sourcery ($12), Qodana ($6 for SAST), Qodo Merge self-hosted ($5-15 API), Claude Code plugin (included), and DIY Actions (API cost only). Ellipsis ($20) and Copilot ($10+ existing sub) are moderate savings. CodeRabbit ($24) saves only $6/mo — negligible.

**Repo context quality ranking:**
1. Claude Code `/code-review` plugin — full repo native (Claude Code already holds the repo)
2. CodeRabbit Pro — best commercial, Codegraph + semantic indexing
3. GitHub Copilot (with agentic tools preview) — directory traversal, CodeQL
4. Qodana — full static analysis graph, not LLM
5. Qodo Merge Enterprise — context engine (paid tier only)
6. Sourcery / Ellipsis / Qodo Merge free — diff-level, limited

**Triggering flexibility:**
- Best CI/CD flexibility: DIY GitHub Actions, Qodo Merge, Qodana
- Good: CodeRabbit (GitHub App auto-triggers), Copilot (GitHub native)
- CLI-first: Claude Code plugin, Qodo Merge CLI, Qodana CLI
- Weakest: Ellipsis, Sourcery (app-only, no CLI)

**Security/bug detection quality:**
- Anthropic's `claude-code-security-review` is purpose-built for 10+ vulnerability classes with Opus-level reasoning
- CodeRabbit runs 40+ SAST tools and synthesizes with LLM
- Qodana excels at deterministic taint analysis (700+ built-in entries)
- Copilot integrates CodeQL natively
- Qodo Merge `/compliance` tool (2025) adds security + ticket requirement checks

**The heurema/fabrica context:**
The project already uses Claude Code (via Claude Max or API subscription). The `/code-review` plugin and `claude-code-action` are zero-cost additions. The sigil plugin (adversarial review) in the heurema ecosystem suggests multi-agent review patterns are already a known approach here.

## Recommendation

**Primary recommendation: Claude Code `/code-review` plugin (zero cost) + DIY `claude-code-security-review` Action.**

1. Install the official `code-review` Claude plugin (`claude plugin add anthropics/code-review`). Use `/code-review --comment` from the terminal or wrap in a CI step using `claude-code-action` to auto-trigger on PR open.
2. Add `anthropics/claude-code-security-review` as a GitHub Actions workflow for automated security scanning on every PR. Configure to run only on trusted (non-fork) PRs.

This combination covers:
- Full repo context (plugin runs inside Claude Code's full file access)
- 5-agent parallel review with confidence filtering
- Security vulnerability detection across 10+ vulnerability classes
- CLI triggerable (`/code-review`) and CI/CD triggerable (GitHub Actions)
- Cost: $0 additional beyond existing Claude subscription + API tokens for the security action (~$5-30/mo depending on PR volume)

**Secondary recommendation (if a passive GitHub bot is required with zero setup):**

Use **GitHub Copilot Code Review** if the team already pays $10/mo for Copilot Pro. Code review is included at no extra cost and context gathering (agentic tools, directory traversal) is now in public preview. Enable it as a required reviewer in branch protection rules.

**If neither Claude subscription nor Copilot exists:**

Self-host **Qodo Merge (PR-Agent)** with Claude Sonnet 4 API key via GitHub Actions. Cost: ~$5-15/mo in API tokens for a moderate PR volume. Full feature set, CLI + CI triggers, open source.

**Do not recommend:**
- CodeRabbit Pro at $24/dev/mo — saves only $6/mo vs Greptile, not worth the switch cost
- Sourcery — repo context too shallow for multi-language/complex codebases
- Ellipsis — insufficient documentation on context depth, smaller community

**Confidence: HIGH** — pricing and feature data gathered from official pricing pages, official documentation, and multiple independent review sources (February 2026). The Claude Code plugin and GitHub Actions recommendations are based on official Anthropic repositories with 100,000+ installs confirmed.
