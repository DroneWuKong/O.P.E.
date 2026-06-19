from __future__ import annotations

from app.config import get_settings
from app.models import ConnectorAction, ConnectorId, ConnectorSpec


def _has_value(value: str | None) -> bool:
    return bool(value and value.strip() and not value.startswith('replace-with'))


def _github_configured() -> bool:
    settings = get_settings()
    token_ready = _has_value(settings.github_token)
    app_ready = _has_value(settings.github_app_id) and _has_value(settings.github_app_private_key)
    return token_ready or app_ready


def _google_oauth_configured() -> bool:
    settings = get_settings()
    return (
        _has_value(settings.google_access_token)
        or _has_value(settings.google_oauth_client_id) and _has_value(settings.google_oauth_client_secret)
    )


def _google_api_token_configured() -> bool:
    settings = get_settings()
    return _has_value(settings.google_access_token)


def _gmail_api_token_configured() -> bool:
    settings = get_settings()
    return _has_value(settings.gmail_access_token) or _has_value(settings.google_access_token)


def _google_service_account_configured() -> bool:
    settings = get_settings()
    return _has_value(settings.google_service_account_json)


def list_connectors() -> list[ConnectorSpec]:
    settings = get_settings()
    google_auth_ready = _google_api_token_configured()
    gmail_auth_ready = _gmail_api_token_configured()

    return [
        ConnectorSpec(
            id='github',
            name='GitHub',
            provider='github.com',
            status='configured' if _github_configured() else 'needs_auth',
            auth_type='token_or_github_app',
            auth_configured=_github_configured(),
            scopes=['repo', 'issues', 'pull_requests', 'actions'],
            actions=[
                ConnectorAction(name='search_repos', description='Search accessible repositories.'),
                ConnectorAction(name='read_file', description='Read a file from an accessible repository.'),
                ConnectorAction(name='create_issue', description='Create a GitHub issue.', read_only=False),
                ConnectorAction(name='comment_on_pr', description='Comment on a pull request.', read_only=False),
                ConnectorAction(name='dispatch_workflow', description='Run an approved GitHub Actions workflow.', read_only=False),
            ],
            notes='Use a fine-grained token or GitHub App installation. O.P.E. never returns the secret value.',
        ),
        ConnectorSpec(
            id='google_drive',
            name='Google Drive',
            provider='google.com',
            status='disabled' if not settings.google_drive_enabled else 'configured' if google_auth_ready else 'needs_auth',
            auth_type='oauth_or_service_account',
            auth_configured=google_auth_ready,
            scopes=['drive.metadata.readonly', 'drive.readonly', 'documents', 'spreadsheets', 'presentations'],
            actions=[
                ConnectorAction(name='search_files', description='Search accessible Drive files.'),
                ConnectorAction(name='read_document', description='Read an accessible Google Doc.'),
                ConnectorAction(name='read_sheet', description='Read an accessible Google Sheet.'),
                ConnectorAction(name='write_document', description='Update an approved Google Doc.', read_only=False),
                ConnectorAction(name='write_sheet', description='Update an approved Google Sheet.', read_only=False),
            ],
            notes='OAuth access tokens are executable now; service accounts are tracked for the next auth-worker slice.',
        ),
        ConnectorSpec(
            id='gmail',
            name='Gmail',
            provider='google.com',
            status='disabled' if not settings.gmail_enabled else 'configured' if gmail_auth_ready else 'needs_auth',
            auth_type='oauth',
            auth_configured=gmail_auth_ready and settings.gmail_enabled,
            scopes=['gmail.readonly', 'gmail.compose', 'gmail.send'],
            actions=[
                ConnectorAction(name='search_mail', description='Search authorized mailbox messages.'),
                ConnectorAction(name='read_thread', description='Read an authorized mail thread.'),
                ConnectorAction(name='draft_reply', description='Draft a reply for operator review.', read_only=False),
            ],
            notes='Disabled by default because mailbox access is sensitive. Sending mail is intentionally not allowlisted yet.',
        ),
    ]


def get_connector(connector_id: ConnectorId) -> ConnectorSpec | None:
    return next((connector for connector in list_connectors() if connector.id == connector_id), None)


def connector_supports_action(connector_id: ConnectorId, action: str) -> bool:
    connector = get_connector(connector_id)
    if connector is None:
        return False
    return any(item.name == action for item in connector.actions)
