from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import uuid

from app.config import get_settings
from app.models import UploadedFileRecord, UploadCategorySuggestion


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


def list_uploads(*, project: str | None = None, category: str | None = None, limit: int = 25) -> list[UploadedFileRecord]:
    category = normalize_category(category)
    records = _load_records()
    if project:
        records = [record for record in records if record.project == project]
    if category:
        records = [record for record in records if record.category == category]
    return sorted(records, key=lambda record: record.created_at, reverse=True)[:limit]


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
        sha256=hashlib.sha256(data).hexdigest(),
        relative_path=relative_path.as_posix(),
        description=description.strip() if description and description.strip() else None,
        created_at=now.isoformat(),
    )
    with _manifest_path().open('a', encoding='utf-8') as manifest:
        manifest.write(record.model_dump_json() + '\n')
    return record
