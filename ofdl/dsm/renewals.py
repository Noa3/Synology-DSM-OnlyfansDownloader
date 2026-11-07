"""Worker-only, opt-in free-page renewals. Trials are website-review only."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from ..common import AppError, Cancelled, Control, EventSink
from . import db as control_db
from .config import Paths
from .jobs import normalize_renewal


def run_offers_scan(paths: Paths, payload: dict[str, Any], control: Control,
                    emit: EventSink) -> dict[str, Any]:
    from ..offers import OfferHistory, scan_offers
    from .run_jobs import _client, _load_session
    account = _load_session(paths).user_id
    emit('phase', 'Free-/Trial-Angebote werden gesucht')
    with _client(paths, control, emit, payload) as client:
        offers = scan_offers(client, control, include_active=True, include_expired=True,
                             include_messages=False, include_inbox=False, include_lists=False,
                             include_promotions=False, extra_profiles=payload.get('profiles', []),
                             history=OfferHistory.load(paths.config / f'free-{account}.json'),
                             emit=lambda kind, value: emit(kind, value) if kind == 'log' else None)
    control.checkpoint()
    rows = [(account, offer.username, offer.kind, offer.status, offer.detail[:300], control_db.now_iso())
            for offer in offers[:2000]]
    with control_db.connect(paths.db) as db:
        db.execute('DELETE FROM offers WHERE account_id=?', (account,))
        db.executemany('INSERT INTO offers VALUES(?,?,?,?,?,?)', rows)
        db.commit()
    return {'offers': len(rows), 'truncated': len(offers) > 2000,
            'message': 'Angebote gespeichert. Trials nur auf der Website bestätigen.'}


def run_free_renew(paths: Paths, payload: dict[str, Any], control: Control,
                   emit: EventSink) -> dict[str, Any]:
    from ..api import ApiError
    from ..offers import FREE, OfferHistory, claim_offer, classify
    from .run_jobs import _client, _load_session
    options = normalize_renewal(payload, require_confirmation=False)
    account = _load_session(paths).user_id
    if str(payload.get('account_id') or '') != account:
        raise AppError('Die Free-Resub-Freigabe gehört zu einem anderen Konto. Bitte erneut bestätigen.')
    history = OfferHistory.load(paths.config / f'free-{account}.json')
    day = datetime.now().date().isoformat()
    counts = {'subscribed': 0, 'skipped': 0, 'errors': 0}
    emit('phase', 'Kostenlose Profile werden erneut geprüft')
    with _client(paths, control, emit, payload) as client:
        for index, name in enumerate(options['profiles']):
            control.checkpoint()
            emit('overall', {'done': index, 'total': len(options['profiles']), 'scanning': False})
            try:
                profile = client.user(name)
                fresh = classify(profile, source='DSM free resub check')
                if (profile.get('subscribedBy') is True or fresh is None
                        or fresh.kind != FREE or fresh.regular_price != 0 or fresh.price != 0):
                    counts['skipped'] += 1
                    emit('log', f'@{name}: bereits abonniert, kostenpflichtig, Trial oder nicht eindeutig kostenlos; übersprungen.')
                    continue
                with control_db.connect(paths.db) as db:
                    db.execute('DELETE FROM renewal_attempts WHERE day < ?', (day,))
                    db.commit()
                    if db.execute('SELECT COUNT(*) FROM renewal_attempts').fetchone()[0] >= 5000:
                        counts['skipped'] += 1
                        emit('log', 'Tageslimit für Anmeldeversuche erreicht; keine weiteren Aktionen.')
                        continue
                    cursor = db.execute('INSERT OR IGNORE INTO renewal_attempts VALUES(?,?,?,?)',
                                        (account, name, day, 'pending'))
                    reserved = cursor.rowcount == 1
                    db.commit()
                if not reserved:
                    counts['skipped'] += 1
                    emit('log', f'@{name}: heute bereits versucht; kein erneuter POST.')
                    continue
                # Existing core re-reads the price immediately before its one
                # non-retried POST. No trial claim endpoint or rebill API used.
                claim_offer(client, fresh, control, history=history, emit=emit)
                with control_db.connect(paths.db) as db:
                    db.execute('UPDATE renewal_attempts SET status=? WHERE account_id=? AND username=? AND day=?',
                               ('completed', account, name, day))
                    db.commit()
                counts['subscribed'] += 1
            except Cancelled:
                raise
            except ApiError as exc:
                if (exc.status in {401, 429} or getattr(exc.details, 'category', '')
                        in {'authentication-rejected', 'invalid-signature', 'refresh-required'}):
                    raise
                counts['errors'] += 1
                emit('log', f'@{name}: API-Fehler; kein automatischer Wiederholungsversuch.')
            except AppError:
                # A timed-out POST has an unknown outcome. Keep the reservation
                # instead of silently issuing another subscription request.
                counts['errors'] += 1
                emit('log', f'@{name}: nicht abgeschlossen; Ergebnis prüfen, kein erneuter POST heute.')
            emit('stats', counts)
            emit('overall', {'done': index + 1, 'total': len(options['profiles']), 'scanning': False})
    return counts
