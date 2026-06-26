# AI Export Intelligence

An automated export intelligence pipeline that discovers and qualifies sales agents or distributors/importers across multiple countries and languages. It searches the web, analyzes company signals, scores commercial fit, extracts contacts, and produces a prioritized lead shortlist.

## Features

- Multilingual discovery for target countries
- Web search and site text analysis
- Fit scoring and partner classification with LLM
- Contact extraction (emails, phones)
- Shortlist ranking
- JSON/CSV/Markdown outputs

## Getting Started

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set your LLM API key:
```bash
export OPENAI_API_KEY="your-api-key-here"
```
Or use Claude:
```bash
export ANTHROPIC_API_KEY="your-api-key-here"
```
Or use Gemini:
```bash
export GEMINI_API_KEY="your-api-key-here"
```
Or use vLLM (OpenAI-compatible server):
```bash
export VLLM_BASE_URL="http://localhost:8001/v1"
export VLLM_API_KEY="token01"
export VLLM_MODEL="meta-llama/Llama-3.3-70B-Instruct"
```

3. Run the pipeline:
```bash
python main.py
```

## Configuration

Command-line flags:

- `--countries` Comma-separated list (default: Germany,Poland,Romania,Czech Republic)
- `--sectors` Comma-separated list (default: industrial automation,packaging,food processing)
- `--max-results` Max web results per query (default: 5)
- `--top` Max shortlisted partners (default: 15)
- `--threshold` Score threshold for shortlist (default: 60)
- `--seeds-file` JSON file with custom seeds
- `--output-dir` Output folder (default: ./outputs)

Example:
```bash
python main.py --countries "Germany,Poland" --sectors "agro machinery" --top 10
python main.py --countries Germany,Poland,Romania,Czech Republic --sectors spin_casting,manifacturers,importers 
```

## Files

- [main.py](main.py) Entry point and CLI
- [flow.py](flow.py) Flow wiring
- [nodes.py](nodes.py) Pipeline nodes
- [utils.py](utils.py) LLM, web search, parsing, and output helpers
- [requirements.txt](requirements.txt) Dependencies

## Output

- `shortlist.json` Full candidate list and shortlist
- `shortlist.csv` Tabular shortlist
- `report.md` Markdown report

## Flow Details

```mermaid
graph LR
	 A[LoadSeeds] --> B[BuildQueries]
	 B --> C[SearchCandidates]
	 C --> D[AnalyzeCandidates]
	 D --> E[ScoreCandidates]
	 E --> F[ExtractContacts]
	 F --> G[DeduplicateCandidates]
	 G --> H[BuildShortlist]
	H --> I[SaveOutputs]
```

1. **LoadSeeds**
	- Loads countries, sectors, keywords, and exclusions from defaults or a seed file.
2. **BuildQueries**
	- Builds multilingual search queries based on countries and sectors.
3. **SearchCandidates**
	- Uses web search to collect candidate sites and evidence snippets.
4. **AnalyzeCandidates**
	- Fetches site text and extracts keyword signals for distributor/agent/importer intent.
5. **ScoreCandidates**
	- Uses the LLM to score fit (0-100), label category, and summarize evidence.
6. **ExtractContacts**
	- Extracts public emails and phone numbers from page text and snippets.
7. **DeduplicateCandidates**
	- Merges results by domain and keeps the best-scoring candidate.
8. **BuildShortlist**
	- Filters and ranks candidates by score and configured threshold/top N.
9. **SaveOutputs**
	 - Writes JSON, CSV, and Markdown outputs to the output directory.

## Notes

- Data sources are public web pages and search results.
- Always verify contact details and compliance before outreach.
