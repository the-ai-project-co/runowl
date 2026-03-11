# RunOwl — Phase 4 Tasks: Integrations & Scale

## 1. Slack Integration

- [ ] Build Slack app configuration
- [ ] Implement OAuth flow for Slack workspace connection
- [ ] Build notification templates:
  - [ ] Review complete (summary with finding counts)
  - [ ] P0/P1 bug found (urgent notification with details)
  - [ ] Tests failed (failure count with links)
  - [ ] Tests passed (green confirmation)
- [ ] Implement channel selection per repository
- [ ] Implement notification preferences (per-user, per-repo, per-severity)
- [ ] Build Slack settings page in web UI
- [ ] Write tests for Slack notifications

## 2. Linear Integration

- [ ] Build Linear API integration
- [ ] Implement OAuth flow for Linear workspace connection
- [ ] Map RunOwl severity levels to Linear priority levels
- [ ] Auto-create Linear issues from findings:
  - [ ] Title: finding summary
  - [ ] Description: full finding details + citations + fix suggestions
  - [ ] Priority: mapped from P0–P3
  - [ ] Labels: bug, security, architecture (based on finding type)
- [ ] Link Linear issues back to PR and finding
- [ ] Build Linear settings page in web UI (project selection, label mapping)
- [ ] Implement bulk issue creation from multiple findings
- [ ] Write tests for Linear integration

## 3. Jira Integration

- [ ] Build Jira API integration (Cloud + Server)
- [ ] Implement OAuth flow for Jira connection
- [ ] Map RunOwl severity levels to Jira priority levels
- [ ] Auto-create Jira issues from findings:
  - [ ] Summary: finding title
  - [ ] Description: full details with code references
  - [ ] Priority: mapped from severity
  - [ ] Issue type: Bug, Security, Task (based on finding type)
  - [ ] Labels/Components: configurable mapping
- [ ] Support Jira project and board selection
- [ ] Link Jira issues back to PR and finding
- [ ] Build Jira settings page in web UI
- [ ] Write tests for Jira integration

## 4. GitLab Support

- [ ] Build GitLab API client (REST + GraphQL)
- [ ] Implement GitLab OAuth authentication
- [ ] Build MR (Merge Request) metadata fetcher
- [ ] Build MR diff fetcher
- [ ] Build file content fetcher for GitLab repos
- [ ] Implement GitLab webhook listener (MR events)
- [ ] Auto-trigger review on MR open
- [ ] Post findings as MR comments (GitLab markdown format)
- [ ] Support GitLab CI integration
- [ ] Build GitLab connection settings page
- [ ] Write tests for GitLab integration

## 5. Bitbucket Support

- [ ] Build Bitbucket API client (REST)
- [ ] Implement Bitbucket OAuth authentication
- [ ] Build PR metadata fetcher for Bitbucket
- [ ] Build PR diff fetcher for Bitbucket
- [ ] Build file content fetcher for Bitbucket repos
- [ ] Implement Bitbucket webhook listener (PR events)
- [ ] Auto-trigger review on PR open
- [ ] Post findings as PR comments (Bitbucket markdown format)
- [ ] Support Bitbucket Pipelines integration
- [ ] Build Bitbucket connection settings page
- [ ] Write tests for Bitbucket integration

## 6. VCS Abstraction Layer

- [ ] Design unified VCS interface (abstract away GitHub/GitLab/Bitbucket)
  - [ ] `fetch_pr_metadata()`
  - [ ] `fetch_pr_diff()`
  - [ ] `fetch_file()`
  - [ ] `post_comment()`
  - [ ] `set_status()`
  - [ ] `search_code()`
  - [ ] `list_directory()`
- [ ] Implement GitHub adapter
- [ ] Implement GitLab adapter
- [ ] Implement Bitbucket adapter
- [ ] Refactor existing code to use abstraction layer
- [ ] Write tests for each adapter against the interface

## 7. Multi-Model Support

- [ ] Design AI provider abstraction interface
  - [ ] `generate()` — single response
  - [ ] `generate_stream()` — streaming response
  - [ ] `embed()` — embeddings (if needed)
- [ ] Implement Gemini provider (existing, refactor to interface)
- [ ] Implement Claude provider (Anthropic API)
- [ ] Implement GPT provider (OpenAI API)
- [ ] Build model selection:
  - [ ] Per-workspace default model
  - [ ] Per-review model override
  - [ ] CLI `--model` flag (extend to support all providers)
- [ ] Implement model-specific prompt tuning
- [ ] Build model settings page in web UI
- [ ] Handle API key management per provider
- [ ] Write tests for each provider
- [ ] Write comparison tests (same PR, different models)

## 8. Custom Review Rules

- [ ] Design rule definition schema (YAML or JSON)
  - [ ] Rule name and description
  - [ ] Pattern to match (regex, AST query, or natural language)
  - [ ] Severity level
  - [ ] Finding type
  - [ ] Fix suggestion template
- [ ] Build rule engine that evaluates custom rules against diffs
- [ ] Build checklist builder UI
  - [ ] Create/edit/delete custom rules
  - [ ] Organize rules into checklists
  - [ ] Enable/disable rules per repository
- [ ] Ship default rule templates (security, performance, accessibility)
- [ ] Import/export rule sets (share across teams)
- [ ] Write tests for rule engine

## 9. PR Analytics Dashboard

- [ ] Design analytics data model
- [ ] Build data collection pipeline (aggregate from reviews and tests)
- [ ] Build dashboard page with charts:
  - [ ] **Merge velocity** — average time from PR open to merge
  - [ ] **Bug trends** — findings per week/month by severity
  - [ ] **Code quality score** — composite score based on findings
  - [ ] **Test pass rate** — percentage of passing tests over time
  - [ ] **Top flagged files** — most frequently reviewed files
  - [ ] **Team activity** — reviews and tests per team member
- [ ] Implement date range filtering
- [ ] Implement per-repo and per-team filtering
- [ ] Build exportable analytics reports
- [ ] Write tests for analytics calculations

## 10. Public REST API

- [ ] Design API specification (OpenAPI/Swagger)
- [ ] Implement API endpoints:
  - [ ] `POST /api/v1/review` — trigger a review
  - [ ] `GET /api/v1/review/:id` — get review results
  - [ ] `POST /api/v1/test` — trigger test generation + execution
  - [ ] `GET /api/v1/test/:id` — get test results
  - [ ] `GET /api/v1/analytics` — get analytics data
  - [ ] `GET /api/v1/rules` — list custom rules
  - [ ] `POST /api/v1/rules` — create custom rule
- [ ] Build API key management
  - [ ] Generate API keys per workspace
  - [ ] Key rotation
  - [ ] Key permissions (read, write, admin)
- [ ] Implement rate limiting per API key
- [ ] Implement usage tracking and metering
- [ ] Build API documentation page (auto-generated from OpenAPI spec)
- [ ] Build API explorer / playground
- [ ] Write API tests

## 11. Monorepo Support

- [ ] Detect monorepo structure (lerna, nx, turborepo, pnpm workspaces)
- [ ] Parse package/service boundaries from config files
- [ ] Scope reviews to affected packages only (based on changed files)
- [ ] Scope test generation to affected packages only
- [ ] Build per-package review configuration
- [ ] Support different review rules per package
- [ ] Display per-package results in UI (grouped findings)
- [ ] Support per-package analytics
- [ ] Write tests for monorepo detection and scoping
