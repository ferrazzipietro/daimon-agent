from __future__ import annotations

import json
import os
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

import yaml


ROOT_DIR = Path(__file__).resolve().parents[2]
MEMORY_PATH = Path(__file__).resolve().parent / "project_memory.json"
LOGS_DIR = Path(__file__).resolve().parent / "logs"
PARTNER_WEB_PROFILES_PATH = Path(__file__).resolve().parent / "partner_web_profiles.json"
INVALID_EXTRACTION_MARKERS = (
    "PDF text was not extracted",
    "Could not extract DOCX text",
    "Install pypdf or provide",
    "Docling is not installed",
)


class DocumentExtractionError(RuntimeError):
    pass


STOPWORDS = {
    "about", "after", "also", "and", "are", "because", "been", "being", "can",
    "could", "does", "for", "from", "have", "how", "into", "its", "more",
    "not", "our", "out", "should", "that", "the", "their", "then", "there",
    "these", "this", "those", "through", "use", "was", "what", "when",
    "where", "which", "while", "with", "work", "would", "you", "your",
}


def call_llm(prompt: str, system: str | None = None) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "your-api-key"))
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    response = client.chat.completions.create(
        model=os.environ.get("OPENAI_MODEL", "gpt-4o"),
        messages=messages,
    )
    return response.choices[0].message.content


def load_env_file(path: str | Path) -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def make_run_id(task: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", task.lower()).strip("-")[:48]
    return f"{timestamp}-{slug or 'proposal-task'}"


def init_run_artifacts(task: str, logs_dir: str | Path | None = None) -> dict:
    run_id = make_run_id(task)
    base_dir = Path(logs_dir) if logs_dir else LOGS_DIR
    run_dir = base_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "trace_json": str(run_dir / "trace.json"),
        "trace_md": str(run_dir / "trace.md"),
        "answer_md": str(run_dir / "answer.md"),
        "answer_pdf": str(run_dir / "answer.pdf"),
    }


def log_step(shared: dict, step: str, details: dict) -> None:
    trace = shared.setdefault("trace", [])
    entry = {
        "index": len(trace) + 1,
        "time": datetime.now().isoformat(timespec="seconds"),
        "step": step,
        "details": details,
    }
    trace.append(entry)
    artifacts = shared.get("artifacts")
    if artifacts:
        write_trace_files(shared)


def write_trace_files(shared: dict) -> None:
    artifacts = shared.get("artifacts")
    if not artifacts:
        return

    trace = shared.get("trace", [])
    Path(artifacts["trace_json"]).write_text(
        json.dumps(
            {
                "run_id": artifacts["run_id"],
                "task": shared.get("task"),
                "note": "This trace contains explicit prompts, retrieved evidence, model-visible outputs, and agent decisions. It does not expose hidden model chain-of-thought.",
                "steps": trace,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    lines = [
        f"# Run Trace: {artifacts['run_id']}",
        "",
        f"Task: {shared.get('task')}",
        "",
        "Note: this trace logs explicit prompts, retrieved evidence, model-visible outputs, and agent decisions. It does not expose hidden model chain-of-thought.",
        "",
    ]
    for entry in trace:
        lines.extend(
            [
                f"## {entry['index']}. {entry['step']}",
                "",
                f"Time: {entry['time']}",
                "",
                "```json",
                json.dumps(entry["details"], indent=2, ensure_ascii=False),
                "```",
                "",
            ]
        )
    Path(artifacts["trace_md"]).write_text("\n".join(lines), encoding="utf-8")


def write_answer_files(shared: dict) -> None:
    artifacts = shared.get("artifacts")
    if not artifacts:
        return

    answer = shared.get("result", shared.get("draft_answer", ""))
    markdown = f"# Answer\n\nTask: {shared.get('task')}\n\n{answer}\n"
    Path(artifacts["answer_md"]).write_text(markdown, encoding="utf-8")
    write_markdown_pdf(artifacts["answer_pdf"], markdown)


def pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def parse_inline_markdown(text: str) -> list[dict]:
    segments = []
    idx = 0
    active = {"bold": False, "italic": False}
    marker_pattern = re.compile(r"(\*\*\*|___|\*\*|__|\*|_)")

    for match in marker_pattern.finditer(text):
        if match.start() > idx:
            segments.append(
                {
                    "text": text[idx : match.start()],
                    "bold": active["bold"],
                    "italic": active["italic"],
                }
            )

        marker = match.group(1)
        if marker in {"***", "___"}:
            active["bold"] = not active["bold"]
            active["italic"] = not active["italic"]
        elif marker in {"**", "__"}:
            active["bold"] = not active["bold"]
        else:
            active["italic"] = not active["italic"]
        idx = match.end()

    if idx < len(text):
        segments.append(
            {
                "text": text[idx:],
                "bold": active["bold"],
                "italic": active["italic"],
            }
        )

    return [segment for segment in segments if segment["text"]]


def segment_font(segment: dict, default_font: str = "F1") -> str:
    if segment.get("code"):
        return "F5"
    if segment.get("bold") and segment.get("italic"):
        return "F4"
    if segment.get("bold"):
        return "F2"
    if segment.get("italic"):
        return "F3"
    return default_font


def strip_inline_markers(text: str) -> str:
    return re.sub(r"(\*\*\*|___|\*\*|__|\*|_)", "", text)


def split_segments_words(segments: list[dict]) -> list[dict]:
    words = []
    for segment in segments:
        for token in re.findall(r"\S+\s*", segment["text"]):
            if token:
                word = dict(segment)
                word["text"] = token
                words.append(word)
    return words


def wrap_segments(segments: list[dict], max_chars: int) -> list[list[dict]]:
    words = split_segments_words(segments)
    if not words:
        return [[]]

    lines = []
    current = []
    current_len = 0
    for word in words:
        word_len = len(word["text"])
        if current and current_len + word_len > max_chars:
            lines.append(current)
            current = []
            current_len = 0
        current.append(word)
        current_len += word_len
    if current:
        lines.append(current)
    return lines


def markdown_to_pdf_lines(markdown: str) -> list[dict]:
    pdf_lines = []
    in_code = False

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()

        if line.strip().startswith("```"):
            in_code = not in_code
            pdf_lines.append({"segments": [], "size": 4, "indent": 50})
            continue

        if in_code:
            pdf_lines.append(
                {
                    "segments": [{"text": line, "code": True}],
                    "size": 9,
                    "indent": 58,
                    "leading": 12,
                }
            )
            continue

        if not line.strip():
            pdf_lines.append({"segments": [], "size": 6, "indent": 50})
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading_match:
            level = len(heading_match.group(1))
            text = strip_inline_markers(heading_match.group(2).strip())
            size = {1: 20, 2: 16, 3: 14}.get(level, 12)
            if pdf_lines:
                pdf_lines.append({"segments": [], "size": 5, "indent": 50})
            pdf_lines.append(
                {
                    "segments": [{"text": text, "bold": True}],
                    "size": size,
                    "indent": 50,
                    "leading": size + 6,
                }
            )
            continue

        bullet_match = re.match(r"^(\s*)[-*+]\s+(.+)$", line)
        if bullet_match:
            level = len(bullet_match.group(1)) // 2
            content = bullet_match.group(2)
            segments = [{"text": "- ", "bold": True}] + parse_inline_markdown(content)
            for idx, wrapped in enumerate(wrap_segments(segments, max(40, 82 - level * 4))):
                pdf_lines.append(
                    {
                        "segments": wrapped if idx == 0 else [{"text": "  "}] + wrapped,
                        "size": 10,
                        "indent": 58 + level * 18,
                        "leading": 13,
                    }
                )
            continue

        numbered_match = re.match(r"^(\s*)(\d+)[.)]\s+(.+)$", line)
        if numbered_match:
            level = len(numbered_match.group(1)) // 2
            prefix = f"{numbered_match.group(2)}. "
            segments = [{"text": prefix, "bold": True}] + parse_inline_markdown(numbered_match.group(3))
            for idx, wrapped in enumerate(wrap_segments(segments, max(40, 82 - level * 4))):
                pdf_lines.append(
                    {
                        "segments": wrapped if idx == 0 else [{"text": " " * len(prefix)}] + wrapped,
                        "size": 10,
                        "indent": 58 + level * 18,
                        "leading": 13,
                    }
                )
            continue

        segments = parse_inline_markdown(line)
        for wrapped in wrap_segments(segments, 92):
            pdf_lines.append(
                {
                    "segments": wrapped,
                    "size": 10,
                    "indent": 50,
                    "leading": 13,
                }
            )
    return pdf_lines


def write_markdown_pdf(path: str | Path, markdown: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rendered_lines = markdown_to_pdf_lines(markdown)
    pages = []
    page = []
    y = 750
    for line in rendered_lines:
        leading = line.get("leading", line.get("size", 10) + 3)
        if y - leading < 50 and page:
            pages.append(page)
            page = []
            y = 750
        page.append(line | {"y": y})
        y -= leading
    if page:
        pages.append(page)
    if not pages:
        pages = [[{"segments": [{"text": ""}], "size": 10, "indent": 50, "y": 750}]]

    objects = []
    objects.append("<< /Type /Catalog /Pages 2 0 R >>")
    page_refs = " ".join(f"{3 + idx * 2} 0 R" for idx in range(len(pages)))
    objects.append(f"<< /Type /Pages /Kids [{page_refs}] /Count {len(pages)} >>")

    for idx, page_lines in enumerate(pages):
        page_obj_num = 3 + idx * 2
        content_obj_num = page_obj_num + 1
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << "
            f"/F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> "
            f"/F2 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >> "
            f"/F3 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Oblique >> "
            f"/F4 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica-BoldOblique >> "
            f"/F5 << /Type /Font /Subtype /Type1 /BaseFont /Courier >> "
            f">> >> "
            f"/Contents {content_obj_num} 0 R >>"
        )

        content_lines = []
        for line in page_lines:
            segments = line.get("segments", [])
            if not segments:
                continue
            size = line.get("size", 10)
            indent = line.get("indent", 50)
            y_pos = line.get("y", 750)
            content_lines.append("BT")
            content_lines.append(f"{indent} {y_pos} Td")
            active_font = None
            for segment in segments:
                text = segment.get("text", "")
                if not text:
                    continue
                font = segment_font(segment)
                if font != active_font:
                    content_lines.append(f"/{font} {size} Tf")
                    active_font = font
                safe_text = pdf_escape(text.encode("latin-1", errors="replace").decode("latin-1"))
                content_lines.append(f"({safe_text}) Tj")
            content_lines.append("ET")
        content = "\n".join(content_lines)
        content_bytes = content.encode("latin-1", errors="replace")
        objects.append(
            f"<< /Length {len(content_bytes)} >>\nstream\n{content}\nendstream"
        )

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj_num, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{obj_num} 0 obj\n".encode("latin-1"))
        pdf.extend(obj.encode("latin-1", errors="replace"))
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))
    pdf.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("latin-1")
    )
    output_path.write_bytes(pdf)


def get_data_dir() -> Path:
    configured = os.environ.get("DAIMON_DATA_DIR")
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            path = Path(__file__).resolve().parent / path
        return path.resolve()
    return ROOT_DIR / "data_daimon"


def load_skills(skills_dir: str | Path) -> dict[str, str]:
    skills = {}
    for md_file in sorted(Path(skills_dir).glob("*.md")):
        skills[md_file.stem] = md_file.read_text(encoding="utf-8")
    if not skills:
        raise ValueError(f"No skill files found in {skills_dir}")
    return skills


def parse_yaml_block(text: str) -> dict:
    match = re.search(r"```ya?ml\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    yaml_text = match.group(1).strip() if match else text.strip()
    return yaml.safe_load(yaml_text) or {}


def get_docling_components():
    try:
        from docling.document_converter import DocumentConverter
    except ImportError as exc:
        raise DocumentExtractionError(
            "Docling is not installed. Install it with `pip install docling` "
            "and rebuild memory. The agent will not fall back to noisy fixed-size chunks."
        ) from exc

    chunker_cls = None
    chunker_import_errors = []
    for import_path, class_name in (
        ("docling_core.transforms.chunker", "HierarchicalChunker"),
        ("docling_core.transforms.chunker.hierarchical_chunker", "HierarchicalChunker"),
        ("docling.chunking", "HierarchicalChunker"),
        ("docling.chunking", "HybridChunker"),
    ):
        try:
            module = __import__(import_path, fromlist=[class_name])
            chunker_cls = getattr(module, class_name)
            break
        except Exception as exc:
            chunker_import_errors.append(f"{import_path}.{class_name}: {exc}")

    return DocumentConverter, chunker_cls, chunker_import_errors


def env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def create_docling_converter(path: Path, DocumentConverter):
    if path.suffix.lower() != ".pdf":
        return DocumentConverter()

    do_ocr = env_flag("DAIMON_DOCLING_OCR", default=False)

    try:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import PdfFormatOption

        pipeline_options = PdfPipelineOptions()
        if hasattr(pipeline_options, "do_ocr"):
            pipeline_options.do_ocr = do_ocr
        if hasattr(pipeline_options, "do_table_structure"):
            pipeline_options.do_table_structure = True

        return DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        )
    except Exception:
        # Older Docling versions may not expose these configuration classes.
        # In that case, continue with the default converter and let strict
        # extraction validation decide whether the result is usable.
        return DocumentConverter()


def convert_with_docling(path: Path):
    DocumentConverter, chunker_cls, chunker_import_errors = get_docling_components()
    converter = create_docling_converter(path, DocumentConverter)
    try:
        result = converter.convert(str(path))
    except Exception as exc:
        hint = ""
        if "OCR" in str(exc) or "PP-OCR" in str(exc):
            hint = (
                " OCR is disabled by default in this agent; if this error persists, "
                "your installed Docling version may ignore the no-OCR option. "
                "Try exporting the PDF as DOCX/TXT or use a Docling version with "
                "PdfPipelineOptions.do_ocr support."
            )
        raise DocumentExtractionError(f"Docling could not convert {path.name}: {exc}.{hint}") from exc

    document = getattr(result, "document", None)
    if document is None:
        document = getattr(result, "output", None)
    if document is None:
        raise DocumentExtractionError(f"Docling conversion produced no document for {path.name}.")
    return document, chunker_cls, chunker_import_errors


def docling_document_to_markdown(document) -> str:
    for method_name in ("export_to_markdown", "export_to_text"):
        method = getattr(document, method_name, None)
        if callable(method):
            try:
                text = clean_text(method())
                if text:
                    return text
            except Exception:
                pass
    return clean_text(str(document))


def docling_chunk_text(chunk) -> str:
    text = getattr(chunk, "text", None)
    if text:
        return clean_text(text)

    for method_name in ("export_to_markdown", "export_to_text"):
        method = getattr(chunk, method_name, None)
        if callable(method):
            try:
                text = clean_text(method())
                if text:
                    return text
            except Exception:
                pass

    return clean_text(str(chunk))


def docling_chunk_metadata(chunk) -> dict:
    meta = getattr(chunk, "meta", None)
    headings = []
    captions = []
    page_numbers = []

    if meta is not None:
        headings = list(getattr(meta, "headings", None) or [])
        captions = list(getattr(meta, "captions", None) or [])
        doc_items = list(getattr(meta, "doc_items", None) or [])
        for item in doc_items:
            prov = getattr(item, "prov", None) or []
            for provenance in prov:
                page_no = getattr(provenance, "page_no", None)
                if page_no is not None:
                    page_numbers.append(page_no)

    return {
        "headings": headings,
        "section_path": " > ".join(str(heading) for heading in headings if heading),
        "captions": captions,
        "page_numbers": sorted(set(page_numbers)),
    }


def chunk_docling_document(path: Path, source_kind: str, priority: str) -> tuple[list[dict], dict]:
    document, chunker_cls, chunker_import_errors = convert_with_docling(path)
    full_text = docling_document_to_markdown(document)
    validate_extracted_text(path.name, full_text)

    chunks = []
    extraction_method = "docling_markdown_sections"
    if chunker_cls is not None:
        try:
            chunker = chunker_cls()
            try:
                raw_chunks = list(chunker.chunk(dl_doc=document))
            except TypeError:
                raw_chunks = list(chunker.chunk(document))
            extraction_method = f"docling_{chunker_cls.__name__}"

            for idx, raw_chunk in enumerate(raw_chunks, start=1):
                text = docling_chunk_text(raw_chunk)
                if not text:
                    continue
                metadata = docling_chunk_metadata(raw_chunk)
                chunks.append(
                    {
                        "id": f"{path.name}#{idx}",
                        "source": path.name,
                        "source_kind": source_kind,
                        "priority": priority,
                        "text": text,
                        "headings": metadata["headings"],
                        "section_path": metadata["section_path"],
                        "captions": metadata["captions"],
                        "page_numbers": metadata["page_numbers"],
                        "chunking": extraction_method,
                    }
                )
        except Exception as exc:
            extraction_method = f"docling_markdown_sections_after_chunker_error: {exc}"

    if not chunks:
        chunks = chunk_markdown_sections(full_text, path.name, source_kind, priority)

    if not chunks:
        raise DocumentExtractionError(f"Docling extracted text from {path.name}, but no usable chunks were produced.")

    for chunk in chunks:
        validate_extracted_text(chunk["id"], chunk["text"])

    source_record = {
        "name": path.name,
        "path": str(path),
        "priority": priority,
        "kind": source_kind,
        "extraction_method": extraction_method,
        "chars": len(full_text),
        "chunks": len(chunks),
        "chunker_import_errors": chunker_import_errors if chunker_cls is None else [],
    }
    return chunks, source_record


def chunk_markdown_sections(text: str, source: str, source_kind: str, priority: str) -> list[dict]:
    chunks = []
    headings = []
    buffer = []

    def flush():
        if not buffer:
            return
        body = clean_text("\n".join(buffer))
        if not body:
            buffer.clear()
            return
        chunks.append(
            {
                "id": f"{source}#{len(chunks) + 1}",
                "source": source,
                "source_kind": source_kind,
                "priority": priority,
                "text": body,
                "headings": headings[:],
                "section_path": " > ".join(headings),
                "captions": [],
                "page_numbers": [],
                "chunking": "docling_markdown_sections",
            }
        )
        buffer.clear()

    for line in text.splitlines():
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", line.strip())
        if heading_match:
            flush()
            level = len(heading_match.group(1))
            heading = heading_match.group(2).strip()
            headings[:] = headings[: level - 1] + [heading]
            continue

        if not line.strip():
            flush()
            continue

        buffer.append(line)

    flush()
    return chunks


def chunk_plain_text_paragraphs(text: str, source: str, source_kind: str, priority: str) -> list[dict]:
    validate_extracted_text(source, text)
    paragraphs = [clean_text(part) for part in re.split(r"\n\s*\n|(?<=\.)\s+(?=[A-ZÀ-ÖØ-Þ])", text)]
    chunks = []
    for paragraph in paragraphs:
        if not paragraph:
            continue
        chunks.append(
            {
                "id": f"{source}#{len(chunks) + 1}",
                "source": source,
                "source_kind": source_kind,
                "priority": priority,
                "text": paragraph,
                "headings": [],
                "section_path": "",
                "captions": [],
                "page_numbers": [],
                "chunking": "plain_text_paragraphs",
            }
        )
    return chunks


def load_partner_web_profiles(path: Path = PARTNER_WEB_PROFILES_PATH) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_partner_name(name: str) -> str:
    name = re.sub(r"\s+", " ", name).strip(" -–—;:,")
    return name


def merge_partner(partners: dict, name: str, **fields) -> None:
    name = normalize_partner_name(name)
    if not name:
        return
    current = partners.setdefault(name, {"name": name})
    for key, value in fields.items():
        if value in (None, "", [], {}):
            continue
        if key == "roles":
            existing = current.setdefault("roles", [])
            for role in value if isinstance(value, list) else [value]:
                if role and role not in existing:
                    existing.append(role)
        elif key == "sources":
            existing = current.setdefault("sources", [])
            for source in value if isinstance(value, list) else [value]:
                if source and source not in existing:
                    existing.append(source)
        elif key == "workpackages":
            existing = current.setdefault("workpackages", [])
            for wp in value if isinstance(value, list) else [value]:
                if wp and wp not in existing:
                    existing.append(wp)
        else:
            if key not in current or not current[key]:
                current[key] = value


def extract_wps(text: str) -> list[str]:
    return sorted(set(re.findall(r"\bWP\s*\d+\b", text, flags=re.IGNORECASE)), key=lambda item: int(re.search(r"\d+", item).group()))


def extract_partners_from_last_news(text: str) -> dict:
    partners = {}
    if re.search(r"Mireia\s+Vendrell", text, flags=re.IGNORECASE):
        merge_partner(
            partners,
            "Mireia Vendrell Morancho",
            location="Barcelona, Spain",
            current_project_role="Data collection in Spain",
            roles=["Data collection in Spain"],
            sources=["last_news.txt"],
        )
    if re.search(r"Desir[ée]e?\s+Schmuck", text, flags=re.IGNORECASE):
        merge_partner(
            partners,
            "Desirée Schmuck",
            location="Vienna, Austria",
            current_project_role="Changes caused by AI in technology users",
            roles=["AI-related changes in technology users"],
            sources=["last_news.txt"],
        )
    return partners


def known_partner_patterns() -> list[dict]:
    return [
        {
            "name": "Fabio Grigenti",
            "unit": "Conceptual-Ethical Analysis",
            "organization": "FISPPA Department, Universita degli Studi di Padova",
            "location": "Padova, Italy",
            "roles": ["Consortium Coordinator"],
            "workpackages": ["WP1", "WP7", "WP8"],
        },
        {
            "name": "Desirée Schmuck",
            "unit": "Media Change and Innovation",
            "organization": "Department of Communication, University of Vienna",
            "location": "Vienna, Austria",
            "roles": [],
            "workpackages": [],
        },
        {
            "name": "Bernardo Magnini",
            "unit": "Technical Model Design",
            "organization": "Natural Language Processing unit, FBK - Fondazione Bruno Kessler",
            "location": "Trento, Italy",
            "roles": [],
            "workpackages": ["WP3"],
        },
        {
            "name": "Antonella Marchetti",
            "unit": "Psychology",
            "organization": "Psychology Department, Universita Cattolica",
            "location": "Milano, Italy",
            "roles": [],
            "workpackages": ["WP4"],
        },
        {
            "name": "Davide Massaro",
            "unit": "Psychology",
            "organization": "Psychology Department, Universita Cattolica",
            "location": "Milano, Italy",
            "roles": [],
            "workpackages": ["WP4"],
        },
        {
            "name": "Ioana R. Podina",
            "unit": "Psychology",
            "organization": "Mind Care 4ALL",
            "location": "Bucharest, Romania",
            "roles": [],
            "workpackages": ["WP5"],
        },
        {
            "name": "Mireia Vendrell Morancho",
            "unit": "Psychology",
            "organization": "Artificial Intelligence Research Institute - Spanish National Research Council",
            "location": "Barcelona, Spain",
            "roles": [],
            "workpackages": ["WP4"],
        },
        {
            "name": "Marco Tamborini",
            "unit": "Philosophy of Technology",
            "organization": "Dipartimento di Filosofia, Pegaso University",
            "location": "Italy",
            "roles": [],
            "workpackages": ["WP2"],
        },
        {
            "name": "Christoph Aurnhammer",
            "unit": "Industrial Partner",
            "organization": "Mentalab",
            "location": "Munich, Germany",
            "roles": ["Industrial partner"],
            "workpackages": ["WP3", "WP5"],
        },
    ]


def extract_partners_from_partner_table(chunks: list[dict]) -> dict:
    table_chunks = [
        chunk for chunk in chunks
        if chunk.get("source", "").lower() == "partners table.pdf"
    ]
    text = "\n".join(chunk.get("text", "") for chunk in table_chunks)
    partners = {}
    if not text:
        return partners

    for item in known_partner_patterns():
        name_pattern = re.escape(item["name"]).replace("\\ ", r"\s+")
        if re.search(name_pattern, text, flags=re.IGNORECASE):
            merge_partner(
                partners,
                item["name"],
                unit=item["unit"],
                organization=item["organization"],
                location=item["location"],
                roles=item["roles"],
                workpackages=item["workpackages"],
                sources=["partners table.pdf"],
            )
    return partners


def enrich_partners_with_web_profiles(partners: dict) -> dict:
    web_profiles = load_partner_web_profiles()
    for name, profile in web_profiles.items():
        if name in partners:
            partners[name]["web_search"] = profile
        else:
            # Keep web-searched profiles only if the researcher is present in
            # project sources; do not add external people from web search alone.
            continue
    return partners


def validate_extracted_text(source_name: str, text: str) -> None:
    cleaned = clean_text(text)
    if not cleaned:
        raise DocumentExtractionError(f"No text extracted from {source_name}.")
    for marker in INVALID_EXTRACTION_MARKERS:
        if marker in cleaned:
            raise DocumentExtractionError(
                f"Invalid extraction marker found in {source_name}. Rebuild memory after fixing extraction."
            )


def validate_memory(memory: dict) -> None:
    bad_chunks = []
    for chunk in memory.get("chunks", []):
        text = chunk.get("text", "")
        if not text.strip() or any(marker in text for marker in INVALID_EXTRACTION_MARKERS):
            bad_chunks.append(chunk.get("id", "(unknown chunk)"))
    if bad_chunks:
        preview = ", ".join(bad_chunks[:5])
        raise DocumentExtractionError(
            "Cached project memory contains invalid extraction placeholder chunks "
            f"({preview}). Rebuild after installing docling or providing convertible source files."
        )
    if not memory.get("partners"):
        raise DocumentExtractionError("No partners were extracted into project memory.")


def clean_text(text: str) -> str:
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def tokenize(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-zA-Z0-9_]+", text.lower())
        if len(token) > 2 and token not in STOPWORDS
    ]


def score_chunk(query_terms: Counter, chunk: dict) -> float:
    body_terms = Counter(tokenize(chunk.get("text", "")))
    heading_text = " ".join(chunk.get("headings", []))
    section_path = chunk.get("section_path", "")
    source_text = " ".join([chunk.get("source", ""), chunk.get("source_kind", "")])
    heading_terms = Counter(tokenize(heading_text + " " + section_path))
    source_terms = Counter(tokenize(source_text))

    score = 0.0
    for term, weight in query_terms.items():
        score += body_terms.get(term, 0) * weight
        score += heading_terms.get(term, 0) * weight * 4
        score += source_terms.get(term, 0) * weight * 0.5

    query_text = " ".join(query_terms.keys())
    heading_text_l = (heading_text + " " + section_path).lower()
    for phrase in extract_query_phrases(query_text):
        if phrase in heading_text_l:
            score += 8

    query_wp = re.findall(r"\bwp\s*0*(\d+)\b", query_text, flags=re.IGNORECASE)
    heading_wp = re.findall(r"\bwp\s*0*(\d+)\b", heading_text_l, flags=re.IGNORECASE)
    for wp in query_wp:
        if wp in heading_wp:
            score += 20

    if re.search(r"\bWP\s*\d+\b", chunk["text"], flags=re.IGNORECASE):
        score += 1.5
    return score


def extract_query_phrases(query_text: str) -> list[str]:
    tokens = tokenize(query_text)
    phrases = []
    for size in (4, 3, 2):
        for idx in range(0, max(0, len(tokens) - size + 1)):
            phrases.append(" ".join(tokens[idx : idx + size]))
    return phrases


def retrieve_context(memory: dict, query: str, top_k: int = 8) -> list[dict]:
    query_terms = Counter(tokenize(query))
    wp_match = re.search(r"\bwp\s*(\d+)\b", query, flags=re.IGNORECASE)
    if wp_match:
        query_terms[f"wp{wp_match.group(1)}"] += 4
        query_terms[f"wp"] += 3
        query_terms[wp_match.group(1)] += 3

    scored = []
    for chunk in memory.get("chunks", []):
        score = score_chunk(query_terms, chunk)
        if score > 0:
            scored.append((score, chunk))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [chunk | {"score": round(score, 2)} for score, chunk in scored[:top_k]]


def infer_intent(task: str) -> str:
    text = task.lower()
    if re.search(r"\bdraft|write|create|compose|generate\b", text):
        if re.search(r"\bwp\s*\d+|work ?package\b", text):
            return "draft_workpackage"
        if "deliverable" in text or "milestone" in text:
            return "design_deliverables"
    if re.search(r"\bmissing|gap|weak|review|improve|critique|think\b", text):
        return "review_workpackage"
    if re.search(r"\bpartner|consortium|lead|who should|which .* work\b", text):
        return "assign_partners"
    if re.search(r"\bcall|expected outcome|scope|alignment|fit|evaluation\b", text):
        return "check_call_alignment"
    if re.search(r"\bdeliverable|milestone|guideline\b", text):
        return "design_deliverables"
    return "proposal_strategy"


def build_project_memory(data_dir: Path | None = None) -> dict:
    data_dir = data_dir or get_data_dir()
    sources = []
    chunks = []

    last_news_path = data_dir / "last_news.txt"
    last_news = last_news_path.read_text(encoding="utf-8") if last_news_path.exists() else ""
    validate_extracted_text(last_news_path.name, last_news)
    partners = extract_partners_from_last_news(last_news)
    last_news_chunks = chunk_plain_text_paragraphs(
        clean_text(last_news),
        last_news_path.name,
        "fresh_updates",
        "highest",
    )
    chunks.extend(last_news_chunks)
    sources.append(
        {
            "name": "last_news.txt",
            "path": str(last_news_path),
            "priority": "highest",
            "kind": "fresh_updates",
            "extraction_method": "plain_text_paragraphs",
            "chars": len(clean_text(last_news)),
            "chunks": len(last_news_chunks),
        }
    )

    call_path = data_dir / "call progetto europeo frictionless.docx"
    if not call_path.exists():
        raise DocumentExtractionError(f"Required call document is missing: {call_path}")
    call_chunks, call_source = chunk_docling_document(
        call_path,
        "horizon_call",
        "authoritative_for_call",
    )
    chunks.extend(call_chunks)
    sources.append(call_source)

    for pdf in sorted(data_dir.glob("*.pdf")):
        pdf_chunks, pdf_source = chunk_docling_document(
            pdf,
            "project_document",
            "project_draft_may_be_outdated",
        )
        chunks.extend(pdf_chunks)
        sources.append(pdf_source)

    for name, partner in extract_partners_from_partner_table(chunks).items():
        merge_partner(
            partners,
            name,
            unit=partner.get("unit"),
            organization=partner.get("organization"),
            location=partner.get("location"),
            roles=partner.get("roles", []),
            workpackages=partner.get("workpackages", []),
            sources=partner.get("sources", []),
        )
    partners = enrich_partners_with_web_profiles(partners)

    memory = {
        "project": {
            "name": "DAIMON Horizon proposal",
            "call_id": "HORIZON-CL2-2026-01-TRANSFO-04",
            "call_title": "The impact of the use of digital tools outside school and for communication on educational outcomes and mental health",
            "action_type": "RIA",
            "proposal_form": "Horizon Europe lump sum, Part B page limit noted in call text as 50 pages",
        },
        "freshness_rules": [
            "Use last_news.txt as the highest-priority source for current consortium and WP decisions.",
            "Use the Horizon call document as authoritative for topic requirements, expected outcomes, scope, and admissibility notes.",
            "Treat WP structure and presentation PDFs as useful project drafts that may contain outdated information.",
            "When sources conflict, explicitly name the conflict and follow the highest-priority source.",
        ],
        "call_requirements": {
            "expected_outcomes": [
                "Solid understanding of how social media, video gaming, and other leisure uses of digital tools relate to young people's educational outcomes, well-being, and mental health.",
                "Rigorous, policy-relevant evidence about policies and practices that inform or regulate non-educational digital tool use, including smartphones at school.",
                "Actionable advice for policymakers and citizens about promoting healthy leisure use of digital tools at school and outside school.",
                "Quantified relationships between leisure/communication digital tool use and motivation, study habits, attention, concentration, time management, engagement, social integration, and well-being.",
            ],
            "scope_requirements": [
                "Address complex, context-dependent effects across device, activity, duration, and setting.",
                "Consider variations by age group, socio-economic background, cultural context, type of digital engagement, and disability.",
                "Apply rigorous experimental and/or quasi-experimental methods, optionally complemented by experience sampling, surveys, and qualitative methods.",
                "Cooperate closely with educational authorities, institutions, and educators.",
                "Include opinions of young people and stakeholders such as media literacy organisations.",
                "Use interdisciplinary SSH approaches where relevant.",
                "Plan clustering and cooperation with other selected or relevant projects.",
                "Consider FAIR data and relevant European research infrastructures where applicable.",
            ],
        },
        "current_updates": [
            "New partner Mireia Vendrell in Barcelona for data collection in Spain.",
            "New partner Desirée Schmuck in Vienna on AI-related changes in technology users.",
            "The consortium is closed.",
            "The separate guidelines WP has been removed; guidelines should become deliverables inside each WP.",
        ],
        "partners": partners,
        "sources": sources,
        "chunks": chunks,
    }
    validate_memory(memory)
    return memory


def load_or_build_memory(force_rebuild: bool = False, data_dir: Path | None = None) -> dict:
    if MEMORY_PATH.exists() and not force_rebuild:
        memory = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
        validate_memory(memory)
        return memory

    memory = build_project_memory(data_dir=data_dir)
    MEMORY_PATH.write_text(json.dumps(memory, indent=2, ensure_ascii=False), encoding="utf-8")
    return memory


def format_context(memory: dict, retrieved: list[dict]) -> str:
    parts = [
        "PROJECT MEMORY SUMMARY",
        yaml.safe_dump(
            {
                "project": memory["project"],
                "freshness_rules": memory["freshness_rules"],
                "current_updates": memory["current_updates"],
                "call_requirements": memory["call_requirements"],
                "partners": memory["partners"],
            },
            sort_keys=False,
            allow_unicode=True,
        ),
        "RETRIEVED SOURCE PASSAGES",
    ]
    for chunk in retrieved:
        metadata = []
        if chunk.get("section_path"):
            metadata.append(f"section={chunk['section_path']}")
        if chunk.get("page_numbers"):
            metadata.append(f"pages={chunk['page_numbers']}")
        if chunk.get("chunking"):
            metadata.append(f"chunking={chunk['chunking']}")
        metadata_text = " | " + " | ".join(metadata) if metadata else ""
        parts.append(
            f"[{chunk['id']} | score={chunk.get('score', 0)}{metadata_text}]\n{chunk['text']}"
        )
    return "\n\n".join(parts)
