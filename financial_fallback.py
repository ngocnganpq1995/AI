"""Supplement missing metrics with explicitly dated CafeF observations."""
from datetime import date
import requests

BASE = 'https://cafef.vn/du-lieu/Ajax/PageNew/'


def finite(value):
    import math
    try:
        value = float(str(value).replace(',', ''))
        return value if math.isfinite(value) else None
    except (ValueError, TypeError):
        return None


def supplement(company):
    summary = company['summary']
    missing = {k for k in ('epsRatio', 'bookValue', 'roe') if finite(summary.get(k)) is None}
    if not missing:
        return company
    notes = {}
    def get(endpoint, params):
        response = requests.get(BASE + endpoint, params=params, timeout=(5, 12))
        response.raise_for_status()
        payload = response.json()
        return payload.get('Data') if payload.get('Success') else None
    try:
        values = get('ChiSoTaiChinh.ashx', {'Symbol': company['ticker']}) or []
        fields = {r.get('Code'): r.get('Value') for r in values}
        period = fields.get('ThoiGian') or 'Kỳ chưa được nguồn ghi rõ'
        for key, code in [('epsRatio', 'EPScoBan'), ('bookValue', 'GiaTriSoSach')]:
            value = finite(fields.get(code))
            if key in missing and value is not None:
                summary[key] = value * 1000
                notes[key] = f'CafeF · {period}' if key == 'epsRatio' else 'CafeF · BVPS hồ sơ; nguồn không ghi kỳ riêng'
    except (requests.RequestException, ValueError, TypeError, AttributeError):
        pass
    if 'roe' in missing:
        try:
            data = get('GetDataChiSoTaiChinh.ashx', {'Symbol': company['ticker'],
                       'TotalRow': 4, 'EndDate': date.today().year, 'ReportType': 'NAM', 'Sort': 'DESC'}) or {}
            reports = sorted(data.get('Value') or [], key=lambda r: finite(r.get('Year')) or 0, reverse=True)
            for report in reports:
                value = next((finite(r.get('Value')) for r in report.get('Value', []) if r.get('Code') == 'ROE'), None)
                if value is not None:
                    summary['roe'] = value
                    notes['roe'] = f"CafeF · ROE năm {report.get('Year', report.get('Time', 'chưa rõ'))}"
                    break
        except (requests.RequestException, ValueError, TypeError, AttributeError):
            pass
    company['metric_notes'] = notes
    return company
