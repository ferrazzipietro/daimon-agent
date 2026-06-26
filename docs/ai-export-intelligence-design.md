# AI Export Intelligence - Design Document

## Overview
This system automates the discovery and qualification of sales agents or distributors/importers in countries specified by the user. It replaces manual keyword-only research with multilingual web discovery, automated site analysis, compatibility scoring, contact extraction, and prioritized shortlists. The system also produces personalized outreach emails and periodic reports.

## Goals
- Discover relevant commercial partners across target countries.
- Search in multiple languages (e.g. English, German, Polish, Romanian, Czech).
- Analyze company websites and classify commercial fit.
- Extract decision-maker contacts when available.
- Produce qualified, prioritized shortlists.
- Generate outreach drafts and scheduled reports.
- Keep data updated with continuous refresh cycles.

## Non-Goals
- Full CRM replacement.
- Automated sending of emails without human review.
- Legal or compliance adjudication (GDPR/legal checks remain human-owned).

## Users
- Export manager / business development team.
- Analysts who review and validate candidate lists.

## Key Data Entities
- Company
  - Name, website, country, sector, size signals, notes.
- Contact
  - Name, role, email, phone, LinkedIn or public profile.
- Evidence
  - Source URL, snippets, timestamps.
- Fit Score
  - Composite score with feature breakdown.
- Shortlist
  - Prioritized list for a country/segment/timeframe.
- Outreach Draft
  - Email subject/body, personalization fields, language.

## High-Level Architecture
- Orchestrator Flow
  - Runs scheduled discovery, analysis, and reporting.
- Search Agents
  - Multilingual query generation and web search.
- Source Parser
  - Fetches and extracts structured signals from websites.
- Classifier
  - Scores commercial fit based on signals.
- Contact Extractor
  - Finds emails and decision-makers from public pages.
- Deduplication + Enrichment
  - Merges duplicates, enriches with additional sources.
- Output Generator
  - Shortlists, outreach drafts, periodic reports.
- Storage
  - Local or external database for companies, contacts, evidence.

## Flow Outline (PocketFlow)
1. Seed Preparation
   - Input: target countries, sectors, keywords, exclusion rules.
2. Multilingual Query Builder
   - Creates language-specific queries and synonyms.
3. Web Search + Candidate Harvest
   - Collects candidate companies and source URLs.
4. Site Analysis
   - Extracts sector signals, territories served, product lines.
5. Fit Scoring
   - Applies weighted scoring and thresholds.
6. Contact Extraction
   - Finds decision makers and commercial contacts.
7. Deduplication
   - Merges duplicates across languages/sources.
8. Shortlist Builder
   - Prioritizes by fit, evidence strength, recency.
9. Outreach Drafting
   - Generates localized email drafts.
10. Reporting
   - Weekly/monthly export intelligence reports.

## Scoring Model (Initial)
- Sector match (0-30)
- Geographic focus (0-20)
- Distributor/agent signals (0-15)
- Company size/reach signals (0-10)
- Contact availability (0-10)
- Evidence freshness (0-10)
- Exclusion penalties (0-20)

## Data Sources
- Public company websites
- Public directories and trade portals
- Chambers of commerce listings
- Industry-specific associations

## Outputs
- Country shortlists (CSV/JSON/Markdown)
- Outreach email drafts per candidate
- Periodic summary reports

## Risks and Mitigations
- False positives: require evidence links and human review.
- Missing data: keep partial records and re-check later.
- Language ambiguity: use multi-language heuristics and fallback rules.
- Compliance: store only public data; add opt-out flags.

## Milestones
1. MVP
   - Multilingual search, basic extraction, shortlist export.
2. v1
   - Fit scoring, contact extraction, report generation.
3. v2
   - Continuous refresh, advanced enrichment, outreach drafts.

## Open Questions
- Preferred database (local JSON vs SQLite vs external)?
- Report cadence and delivery channel?
- Preferred email templates and brand tone?
- Any sector-specific exclusion rules?
