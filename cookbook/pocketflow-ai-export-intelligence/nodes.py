import json
import os

import yaml
from pocketflow import Node
from utils import (
    DEFAULT_SEEDS,
    build_queries,
    call_llm,
    chunked,
    extract_emails,
    extract_phones,
    fetch_page_text,
    keyword_signals,
    normalize_domain,
    safe_yaml_list,
    search_web,
    timestamp,
    write_csv,
    write_json,
    write_markdown,
)


class LoadSeeds(Node):
    def prep(self, shared):
        return shared

    def exec(self, shared):
        seeds = shared.get("seeds", DEFAULT_SEEDS)
        seeds_file = shared.get("seeds_file")
        if seeds_file and os.path.exists(seeds_file):
            with open(seeds_file, "r", encoding="utf-8") as f:
                seeds = json.load(f)
        print(f"  Seeds: countries={len(seeds.get('countries', []))} sectors={len(seeds.get('sectors', []))}")
        return seeds

    def post(self, shared, prep_res, exec_res):
        shared["seeds"] = exec_res
        shared["run_id"] = timestamp()
        print("Loaded seeds")


class BuildQueries(Node):
    def prep(self, shared):
        return shared["seeds"]

    def exec(self, seeds):
        return build_queries(seeds)

    def post(self, shared, prep_res, exec_res):
        shared["queries"] = exec_res
        print(f"Built {len(exec_res)} queries")


class SearchCandidates(Node):
    def prep(self, shared):
        return {
            "queries": shared["queries"],
            "max_results": shared.get("max_results", 5),
        }

    def exec(self, data):
        candidates = []
        seen = set()
        for i, entry in enumerate(data["queries"], 1):
            query = entry["query"]
            print(f"  Search {i}/{len(data['queries'])}: {query}")
            try:
                results = search_web(query, max_results=data["max_results"])
            except Exception as exc:
                print(f"  Search failed: {exc}")
                results = []
            print(f"  Results: {len(results)}")
            for r in results:
                url = r.get("href")
                if not url or url in seen:
                    continue
                seen.add(url)
                candidates.append(
                    {
                        "name": r.get("title") or "",
                        "url": url,
                        "snippet": r.get("body") or "",
                        "title": r.get("title") or "",
                        "country": entry["country"],
                        "language": entry["language"],
                        "evidence": [
                            {
                                "query": query,
                                "url": url,
                                "title": r.get("title") or "",
                                "snippet": r.get("body") or "",
                            }
                        ],
                    }
                )
        return candidates

    def post(self, shared, prep_res, exec_res):
        shared["candidates"] = exec_res
        print(f"Collected {len(exec_res)} candidates")


class AnalyzeCandidates(Node):
    def prep(self, shared):
        return shared["candidates"]

    def exec(self, candidates):
        enriched = []
        for i, c in enumerate(candidates, 1):
            if i <= 5:
                print(f"  Fetch {i}/{len(candidates)}: {c.get('url', '')}")
            text = fetch_page_text(c["url"])
            if not text:
                print(f"  Empty page text for: {c.get('url', '')}")
            signals = keyword_signals(" ".join([c.get("snippet", ""), text]), c["language"])
            c["page_text"] = text
            c["signals"] = signals
            enriched.append(c)
        return enriched

    def post(self, shared, prep_res, exec_res):
        shared["candidates"] = exec_res
        print("Analyzed candidate pages")


class ScoreCandidates(Node):
    def prep(self, shared):
        return shared["candidates"]

    def exec(self, candidates):
        scored = []
        for batch_idx, batch in enumerate(chunked(candidates, 8), 1):
            print(f"  Scoring batch {batch_idx} ({len(batch)} candidates)")
            batch_text = "\n".join(
                f"- URL: {c['url']}\n  Name: {c['name']}\n  Country: {c['country']}\n  Snippet: {c['snippet']}\n  Signals: {c['signals']}"
                for c in batch
            )
            prompt = f"""You are scoring commercial partners for export development.
Score each candidate 0-100 based on fit as agent/distributor/importer.
Return YAML only.

Candidates:
{batch_text}

Output format:
```yaml
scores:
  - url: "..."
    score: 72
    category: "distributor"  # distributor|agent|importer|other
    reason: "one sentence"
    confidence: 0.0
    fit_tags: ["keyword", "region"]
```"""
            resp = call_llm(prompt)
            scores = safe_yaml_list(resp, "scores")
            if not scores:
                print("  Warning: no scores returned for batch")
            score_map = {s.get("url"): s for s in scores}
            for c in batch:
                s = score_map.get(c["url"], {})
                c["score"] = int(s.get("score", 0))
                c["category"] = s.get("category", "other")
                c["score_reason"] = s.get("reason", "")
                c["confidence"] = s.get("confidence", 0.0)
                c["fit_tags"] = s.get("fit_tags", [])
                scored.append(c)
        return scored

    def post(self, shared, prep_res, exec_res):
        shared["candidates"] = exec_res
        print("Scored candidates")


class ExtractContacts(Node):
    def prep(self, shared):
        return shared["candidates"]

    def exec(self, candidates):
        for c in candidates:
            text = " ".join([c.get("snippet", ""), c.get("page_text", "")])
            c["contact_emails"] = extract_emails(text)
            c["contact_phones"] = extract_phones(text)
        print(f"  Contacts extracted for {len(candidates)} candidates")
        return candidates

    def post(self, shared, prep_res, exec_res):
        shared["candidates"] = exec_res
        print("Extracted contacts")


class DeduplicateCandidates(Node):
    def prep(self, shared):
        return shared["candidates"]

    def exec(self, candidates):
        best = {}
        for c in candidates:
            domain = normalize_domain(c.get("url"))
            if not domain:
                continue
            existing = best.get(domain)
            if not existing or c.get("score", 0) > existing.get("score", 0):
                best[domain] = c
            else:
                existing["evidence"].extend(c.get("evidence", []))
                existing["contact_emails"] = sorted(
                    set(existing.get("contact_emails", [])) | set(c.get("contact_emails", []))
                )
                existing["contact_phones"] = sorted(
                    set(existing.get("contact_phones", [])) | set(c.get("contact_phones", []))
                )
        return list(best.values())

    def post(self, shared, prep_res, exec_res):
        shared["candidates"] = exec_res
        print("Deduplicated candidates")


class BuildShortlist(Node):
    def prep(self, shared):
        return {
            "candidates": shared["candidates"],
            "threshold": shared.get("score_threshold", 60),
            "top_n": shared.get("top_n", 15),
        }

    def exec(self, data):
        ranked = sorted(data["candidates"], key=lambda c: c.get("score", 0), reverse=True)
        shortlist = [c for c in ranked if c.get("score", 0) >= data["threshold"]]
        return ranked, shortlist[: data["top_n"]]

    def post(self, shared, prep_res, exec_res):
        ranked, shortlist = exec_res
        shared["ranked"] = ranked
        shared["shortlist"] = shortlist
        print(f"Shortlist size: {len(shortlist)}")


class SaveOutputs(Node):
    def prep(self, shared):
        return shared

    def exec(self, shared):
        output_dir = shared.get("output_dir")
        run_id = shared.get("run_id")
        ranked = shared.get("ranked", [])
        shortlist = shared.get("shortlist", [])

        print(f"  Writing outputs to: {output_dir}")

        json_path = os.path.join(output_dir, f"shortlist_{run_id}.json")
        csv_path = os.path.join(output_dir, f"shortlist_{run_id}.csv")
        md_path = os.path.join(output_dir, f"report_{run_id}.md")

        write_json(json_path, {"ranked": ranked, "shortlist": shortlist})
        write_csv(
            csv_path,
            shortlist,
            ["name", "url", "country", "category", "score", "score_reason", "contact_emails", "contact_phones"],
        )

        md_lines = ["# AI Export Intelligence Report", "", f"Total candidates: {len(ranked)}", f"Shortlist: {len(shortlist)}", ""]
        for i, c in enumerate(shortlist, 1):
            md_lines.append(f"## {i}. {c.get('name','')}")
            md_lines.append(f"- URL: {c.get('url','')}")
            md_lines.append(f"- Country: {c.get('country','')}")
            md_lines.append(f"- Category: {c.get('category','')}")
            md_lines.append(f"- Score: {c.get('score','')}")
            md_lines.append(f"- Reason: {c.get('score_reason','')}")
            md_lines.append("")
        write_markdown(md_path, "\n".join(md_lines))

        return {"json": json_path, "csv": csv_path, "md": md_path}

    def post(self, shared, prep_res, exec_res):
        shared["outputs"] = exec_res
        print("Saved outputs")
