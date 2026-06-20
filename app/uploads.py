from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import uuid

from app.config import get_settings
from app.models import UploadedFileRecord, UploadCategorySuggestion, UploadStatsResponse


CATEGORY_ALIASES = {
    'receipt': 'receipts',
    'receipts': 'receipts',
    'bill': 'bills',
    'bills': 'bills',
    'invoice': 'invoices',
    'invoices': 'invoices',
    'statement': 'statements',
    'statements': 'statements',
    'tax': 'taxes',
    'taxes': 'taxes',
    'medical': 'medical',
    'insurance': 'insurance',
    'warranty': 'warranties',
    'warranties': 'warranties',
    'home': 'home',
    'vehicle': 'vehicle',
    'bank': 'banking',
    'banking': 'banking',
}

CATEGORY_KEYWORDS = [
    ('receipts', ['receipt', 'purchase', 'paid', 'order']),
    ('bills', ['bill', 'due', 'utility', 'electric', 'gas', 'water', 'internet', 'phone']),
    ('invoices', ['invoice', 'estimate', 'quote']),
    ('statements', ['statement', 'account', 'balance']),
    ('taxes', ['tax', 'w2', '1099', 'irs', 'property-tax']),
    ('medical', ['medical', 'doctor', 'clinic', 'hospital', 'pharmacy', 'prescription']),
    ('insurance', ['insurance', 'policy', 'claim']),
    ('warranties', ['warranty', 'manual', 'serial']),
    ('home', ['mortgage', 'lease', 'rent', 'contractor', 'repair', 'hvac', 'plumbing']),
    ('vehicle', ['vehicle', 'auto', 'car', 'truck', 'oil', 'registration', 'dmv']),
    ('banking', ['bank', 'credit-card', 'debit', 'loan']),
]

VENDOR_STOPWORDS = {
    'receipt',
    'invoice',
    'statement',
    'bill',
    'total',
    'amount',
    'date',
    'page',
}

DATE_PATTERNS = [
    re.compile(r'\b(?P<date>\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b'),
    re.compile(r'\b(?P<date>(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4})\b', re.I),
]

AMOUNT_PATTERNS = [
    re.compile(r'(?:grand\s+total|amount\s+due|total|balance\s+due)\s*[:#-]?\s*\$?\s*(?P<amount>\d{1,4}(?:,\d{3})*(?:\.\d{2})?)', re.I),
    re.compile(r'\$\s*(?P<amount>\d{1,4}(?:,\d{3})*(?:\.\d{2})?)'),
]

ACCOUNT_PATTERNS = [
    re.compile(r'(?:account|acct|invoice|reference|ref|confirmation|order)\s*(?:no\.?|number|#|id)?\s*[:#-]?\s*(?P<value>[A-Z0-9][A-Z0-9-]{3,})', re.I),
]


def upload_root() -> Path:
    root = Path(get_settings().ope_upload_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _manifest_path() -> Path:
    return upload_root() / '.ope_upload_manifest.jsonl'


def _safe_segment(value: str | None, fallback: str) -> str:
    cleaned = re.sub(r'[^A-Za-z0-9._-]+', '-', (value or '').strip()).strip('.-_')
    return cleaned[:80] or fallback


def normalize_category(value: str | None) -> str | None:
    if not value:
        return None
    key = _safe_segment(value.lower().replace(' ', '-'), 'inbox')
    return CATEGORY_ALIASES.get(key, key)


def _clean_text(value: str) -> str:
    value = value.replace('\x00', ' ')
    value = re.sub(r'[ \t\r\f\v]+', ' ', value)
    value = re.sub(r'\n{3,}', '\n\n', value)
    return value.strip()


def _decode_text_bytes(data: bytes) -> str:
    for encoding in ('utf-8', 'utf-16', 'latin-1'):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = data.decode('latin-1', errors='ignore')
    printable = ''.join(ch if ch == '\n' or ch == '\t' or 32 <= ord(ch) <= 126 else ' ' for ch in text)
    return _clean_text(printable)


def _run_text_extractor(command: list[str], data: bytes, suffix: str) -> str:
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
        handle.write(data)
        path = Path(handle.name)
    try:
        result = subprocess.run(
            [arg.format(path=str(path)) for arg in command],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            return _clean_text(result.stdout)
        return ''
    except (OSError, subprocess.TimeoutExpired):
        return ''
    finally:
        path.unlink(missing_ok=True)


def extract_text(filename: str, content_type: str | None, data: bytes) -> tuple[str, str]:
    suffix = Path(filename or '').suffix.lower()
    if content_type and content_type.startswith('text/') or suffix in {'.txt', '.csv', '.md'}:
        return _decode_text_bytes(data), 'text'
    if content_type == 'application/pdf' or suffix == '.pdf':
        if shutil.which('pdftotext'):
            text = _run_text_extractor(['pdftotext', '-layout', '{path}', '-'], data, '.pdf')
            if text:
                return text, 'pdftotext'
        return _decode_text_bytes(data), 'pdf-sniff'
    if (content_type and content_type.startswith('image/')) or suffix in {'.jpg', '.jpeg', '.png', '.webp', '.tif', '.tiff'}:
        if shutil.which('tesseract'):
            text = _run_text_extractor(['tesseract', '{path}', 'stdout'], data, suffix or '.png')
            if text:
                return text, 'tesseract'
        return '', 'ocr-unavailable'
    return _decode_text_bytes(data), 'binary-sniff'


def _first_meaningful_line(text: str) -> str | None:
    for line in text.splitlines():
        cleaned = re.sub(r'[^A-Za-z0-9 &.,\'-]+', ' ', line).strip()
        if len(cleaned) < 3:
            continue
        if cleaned.lower() in VENDOR_STOPWORDS:
            continue
        if re.search(r'[A-Za-z]', cleaned):
            return cleaned[:80]
    return None


def extract_fields(text: str, filename: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    haystack = _clean_text(text)
    vendor = _first_meaningful_line(haystack)
    if vendor:
        fields['vendor'] = vendor
    for pattern in DATE_PATTERNS:
        match = pattern.search(haystack)
        if match:
            fields['date'] = match.group('date')
            break
    for pattern in AMOUNT_PATTERNS:
        match = pattern.search(haystack)
        if match:
            fields['amount'] = match.group('amount').replace(',', '')
            break
    for pattern in ACCOUNT_PATTERNS:
        match = pattern.search(haystack)
        if match:
            fields['reference'] = match.group('value')
            break
    if not fields:
        filename_hint = Path(filename or '').stem.replace('-', ' ').replace('_', ' ').strip()
        if filename_hint:
            fields['filename_hint'] = filename_hint[:80]
    return fields


def suggest_category(filename: str, content_type: str | None = None) -> UploadCategorySuggestion:
    haystack = filename.lower().replace('_', '-').replace(' ', '-')
    for category, keywords in CATEGORY_KEYWORDS:
        if any(keyword in haystack for keyword in keywords):
            return UploadCategorySuggestion(category=category, confidence=0.82, reason='matched filename')
    if content_type == 'application/pdf':
        return UploadCategorySuggestion(category='documents', confidence=0.35, reason='pdf document')
    if content_type and content_type.startswith('image/'):
        return UploadCategorySuggestion(category='receipts', confidence=0.4, reason='image upload')
    return UploadCategorySuggestion(category='inbox', confidence=0.15, reason='needs operator review')


def _load_records() -> list[UploadedFileRecord]:
    path = _manifest_path()
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        try:
            records.append(UploadedFileRecord.model_validate_json(line))
        except Exception:
            continue
    return records


def list_uploads(
    *,
    project: str | None = None,
    category: str | None = None,
    query: str | None = None,
    needs_review: bool | None = None,
    limit: int = 25,
) -> list[UploadedFileRecord]:
    category = normalize_category(category)
    records = _load_records()
    if project:
        records = [record for record in records if record.project == project]
    if category:
        records = [record for record in records if record.category == category]
    if needs_review is not None:
        records = [record for record in records if record.needs_review is needs_review]
    if query and query.strip():
        needle = query.strip().lower()
        records = [
            record for record in records
            if needle in ' '.join([
                record.original_filename,
                record.category,
                record.description or '',
                record.extracted_text_preview or '',
                record.duplicate_of or '',
                json.dumps(record.extracted_fields, sort_keys=True),
            ]).lower()
        ]
    return sorted(records, key=lambda record: record.created_at, reverse=True)[:limit]


def upload_stats(*, project: str | None = None) -> UploadStatsResponse:
    records = _load_records()
    if project:
        records = [record for record in records if record.project == project]
    by_category: dict[str, int] = {}
    for record in records:
        by_category[record.category] = by_category.get(record.category, 0) + 1
    return UploadStatsResponse(
        project=project,
        total=len(records),
        total_bytes=sum(record.size_bytes for record in records),
        needs_review=sum(1 for record in records if record.needs_review),
        duplicates=sum(1 for record in records if record.duplicate_of),
        by_category=dict(sorted(by_category.items())),
    )


def find_upload(upload_id: str) -> UploadedFileRecord | None:
    for record in _load_records():
        if record.id == upload_id:
            return record
    return None


def uploaded_file_path(record: UploadedFileRecord) -> Path:
    root = upload_root()
    path = (root / record.relative_path).resolve()
    if not path.is_relative_to(root):
        raise ValueError('upload path escaped upload root')
    return path


def _write_records(records: list[UploadedFileRecord]) -> None:
    path = _manifest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as manifest:
        for record in records:
            manifest.write(record.model_dump_json() + '\n')


def update_upload(
    upload_id: str,
    *,
    category: str | None = None,
    description: str | None = None,
    needs_review: bool | None = None,
) -> UploadedFileRecord | None:
    records = _load_records()
    updated: UploadedFileRecord | None = None
    for index, record in enumerate(records):
        if record.id != upload_id:
            continue
        updates: dict[str, object] = {}
        if category is not None:
            next_category = normalize_category(category) or record.category
            updates['category'] = next_category
            if next_category != record.category:
                old_path = uploaded_file_path(record)
                parts = Path(record.relative_path).parts
                if len(parts) >= 5:
                    new_relative = Path(parts[0]) / _safe_segment(next_category, 'inbox') / Path(*parts[2:])
                    new_path = upload_root() / new_relative
                    new_path.parent.mkdir(parents=True, exist_ok=True)
                    if old_path.exists():
                        old_path.replace(new_path)
                    updates['relative_path'] = new_relative.as_posix()
        if description is not None:
            updates['description'] = description.strip() or None
        if needs_review is not None:
            updates['needs_review'] = needs_review
            if not needs_review:
                updates['review_reason'] = None
        updated = record.model_copy(update=updates)
        records[index] = updated
        break
    if updated:
        _write_records(records)
    return updated


def delete_upload(upload_id: str) -> UploadedFileRecord | None:
    records = _load_records()
    kept = []
    removed: UploadedFileRecord | None = None
    for record in records:
        if record.id == upload_id:
            removed = record
            continue
        kept.append(record)
    if removed:
        uploaded_file_path(removed).unlink(missing_ok=True)
        _write_records(kept)
    return removed


def save_upload(
    *,
    filename: str,
    content_type: str | None,
    data: bytes,
    project: str | None,
    category: str | None,
    description: str | None = None,
) -> UploadedFileRecord:
    settings = get_settings()
    if not data:
        raise ValueError('uploaded file is empty')
    if len(data) > settings.ope_upload_max_bytes:
        raise ValueError(f'uploaded file is larger than {settings.ope_upload_max_bytes} bytes')

    file_hash = hashlib.sha256(data).hexdigest()
    existing_records = _load_records()
    duplicate_matches = [
        record for record in existing_records
        if record.sha256 == file_hash and record.project == (project or settings.ope_default_project)
    ]
    duplicate_source = duplicate_matches[0] if duplicate_matches else None
    suggestion = suggest_category(filename, content_type)
    final_category = normalize_category(category) or suggestion.category
    now = datetime.now(timezone.utc)
    project_segment = _safe_segment(project or settings.ope_default_project, 'default')
    category_segment = _safe_segment(final_category, 'inbox')
    original_name = Path(filename or 'upload.bin').name
    safe_name = _safe_segment(original_name, 'upload.bin')
    suffix = Path(safe_name).suffix[:16]
    upload_id = str(uuid.uuid4())
    stored_filename = f'{now.strftime("%Y%m%d-%H%M%S")}-{upload_id[:8]}{suffix}'
    relative_path = Path(project_segment) / category_segment / now.strftime('%Y') / now.strftime('%m') / stored_filename
    destination = upload_root() / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    extracted_text, extraction_method = extract_text(original_name, content_type, data)
    extracted = extract_fields(extracted_text, original_name)
    text_preview = extracted_text[:500] if extracted_text else None
    needs_review = suggestion.confidence < 0.7 or not extracted or duplicate_source is not None
    review_reason = None
    if needs_review:
        if duplicate_source:
            review_reason = f'Duplicate of {duplicate_source.original_filename}'
        elif not extracted_text and extraction_method == 'ocr-unavailable':
            review_reason = 'OCR unavailable for image; operator review needed'
        elif not extracted:
            review_reason = 'No receipt/bill metadata extracted'
        else:
            review_reason = 'Low category confidence'

    record = UploadedFileRecord(
        id=upload_id,
        project=project or settings.ope_default_project,
        original_filename=original_name,
        stored_filename=stored_filename,
        category=final_category,
        suggested_category=suggestion.category,
        confidence=suggestion.confidence,
        content_type=content_type,
        size_bytes=len(data),
        sha256=file_hash,
        relative_path=relative_path.as_posix(),
        description=description.strip() if description and description.strip() else None,
        extracted_text_preview=text_preview,
        extracted_fields={**extracted, 'extraction_method': extraction_method},
        needs_review=needs_review,
        review_reason=review_reason,
        duplicate_of=duplicate_source.id if duplicate_source else None,
        duplicate_count=len(duplicate_matches),
        created_at=now.isoformat(),
    )
    with _manifest_path().open('a', encoding='utf-8') as manifest:
        manifest.write(record.model_dump_json() + '\n')
    return record
