"""Calendar month reporting in Moscow time; never substitute stale audience data."""
from dataclasses import dataclass
from datetime import date
import pandas as pd
from sqlalchemy import select
from storage import Account, AudienceSnapshot, Company
from analysis import post_frame

REPORT_TZ = 'Europe/Moscow'
MONTHS = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь', 'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь']
PLATFORM_NAMES = {'pulse': 'Пульс', 'telegram': 'Telegram', 'vk': 'ВКонтакте', 'smartlab': 'Смартлаб', 'alfa_investor': 'Альфа-Инвестор', 'bcs_profit': 'БКС Профит'}


@dataclass(frozen=True)
class ReportWindow:
    report_start: pd.Timestamp
    current_start: pd.Timestamp
    previous_start: pd.Timestamp

    @property
    def snapshot_date(self):
        return (self.report_start-pd.Timedelta(days=1)).date()

    @property
    def previous_snapshot_date(self):
        return (self.current_start-pd.Timedelta(days=1)).date()

    @property
    def label(self):
        return f'{MONTHS[self.report_start.month-1]} {self.report_start.year}'

    @property
    def data_label(self):
        return f'{MONTHS[self.current_start.month-1]} {self.current_start.year}'


def report_window(month):
    value = pd.Timestamp(month)
    value = value.tz_localize(REPORT_TZ) if value.tzinfo is None else value.tz_convert(REPORT_TZ)
    report = value.normalize().replace(day=1)
    return ReportWindow(report, report-pd.offsets.MonthBegin(1), report-pd.offsets.MonthBegin(2))


def on_date(snapshots, day):
    """Latest observation on the exact local calendar day, never an earlier day."""
    matches = [s for s in snapshots if pd.Timestamp(s.observed_at).tz_convert(REPORT_TZ).date() == day]
    return max(matches, key=lambda s: pd.Timestamp(s.observed_at)) if matches else None


def sum_complete(values):
    return sum(values) if values and all(v is not None and not pd.isna(v) for v in values) else None


def change(current, previous):
    delta = current-previous if current is not None and previous is not None else None
    percent = delta/previous*100 if delta is not None and previous > 0 else None
    return delta, percent


def audience_report(factory, window, platforms=('pulse', 'telegram'), company_ids=None):
    """One row per company/platform + a complete-only total of supplied accounts."""
    records, details = [], []
    with factory() as session:
        companies = list(session.scalars(select(Company)))
        accounts = list(session.scalars(select(Account)))
        all_snapshots = list(session.scalars(select(AudienceSnapshot)))
        for company in companies:
            if company_ids is not None and company.id not in company_ids:
                continue
            total_current, total_previous = [], []
            for platform in platforms:
                matching = [a for a in accounts if a.company_id == company.id and a.platform == platform]
                current_values, previous_values = [], []
                for account in matching:
                    snapshots = [s for s in all_snapshots if s.account_pk == account.id]
                    current = on_date(snapshots, window.snapshot_date)
                    previous = on_date(snapshots, window.previous_snapshot_date)
                    current_values.append(current.followers if current else None)
                    previous_values.append(previous.followers if previous else None)
                    details.append(dict(company_id=company.id, company=company.name, platform=platform, account_id=account.account_id,
                                        target_date=window.snapshot_date, previous_target_date=window.previous_snapshot_date,
                                        observed_at=current.observed_at if current else None,
                                        previous_observed_at=previous.observed_at if previous else None,
                                        collected_at=current.collected_at if current else None,
                                        previous_collected_at=previous.collected_at if previous else None,
                                        source_url=current.source_url if current else account.source_url,
                                        verification=account.verification))
                current, previous = sum_complete(current_values), sum_complete(previous_values)
                delta, percent = change(current, previous)
                records.append(dict(company_id=company.id, company=company.name, role=company.role, platform=platform,
                                    followers=current, previous_followers=previous, delta=delta, delta_pct=percent,
                                    provided_accounts=len(matching), observed_accounts=sum(v is not None for v in current_values),
                                    previous_observed_accounts=sum(v is not None for v in previous_values)))
                total_current.extend(current_values)
                total_previous.extend(previous_values)
            current, previous = sum_complete(total_current), sum_complete(total_previous)
            delta, percent = change(current, previous)
            records.append(dict(company_id=company.id, company=company.name, role=company.role, platform='total',
                                followers=current, previous_followers=previous, delta=delta, delta_pct=percent,
                                provided_accounts=len(total_current), observed_accounts=sum(v is not None for v in total_current),
                                previous_observed_accounts=sum(v is not None for v in total_previous)))
    columns = ['company_id', 'company', 'role', 'platform', 'followers', 'previous_followers', 'delta', 'delta_pct', 'provided_accounts', 'observed_accounts', 'previous_observed_accounts']
    detail_columns = ['company_id', 'company', 'platform', 'account_id', 'target_date', 'previous_target_date', 'observed_at', 'previous_observed_at', 'collected_at', 'previous_collected_at', 'source_url', 'verification']
    return pd.DataFrame(records, columns=columns), pd.DataFrame(details, columns=detail_columns)


def monthly_posts(factory, window, platforms, company_ids):
    # Metrics after month-end must not leak into the historical report.
    frame = post_frame(factory, now=window.report_start, observed_before=window.report_start)
    if frame.empty:
        return frame
    published = pd.to_datetime(frame.published_at, utc=True)
    frame = frame.loc[(published >= window.current_start) & (published < window.report_start) &
                      (frame.kind == 'official') & frame.platform.isin(platforms) & frame.company_id.isin(company_ids)].copy()
    if not frame.empty:
        measured = pd.to_datetime(frame.observed_at, utc=True).dt.tz_convert(REPORT_TZ).dt.date
        frame['month_end_metric'] = measured == window.snapshot_date
    else:
        frame['month_end_metric'] = pd.Series(dtype=bool)
    return frame


def monthly_activity(factory, window, platforms, company_ids):
    """Counts are sample counts; no coverage inference from an absent post."""
    frame = post_frame(factory, observed_before=window.report_start, now=window.report_start)
    current_counts, previous_counts = {}, {}
    if not frame.empty:
        frame = frame.loc[(frame.kind == 'official') & frame.platform.isin(platforms)]
        times = pd.to_datetime(frame.published_at, utc=True)
        current_counts = frame.loc[(times >= window.current_start) & (times < window.report_start)].groupby('company_id').size().to_dict()
        previous_counts = frame.loc[(times >= window.previous_start) & (times < window.current_start)].groupby('company_id').size().to_dict()
    return pd.DataFrame([dict(company_id=c, current_posts=current_counts.get(c, 0), previous_posts=previous_counts.get(c, 0),
                              delta=current_counts.get(c, 0)-previous_counts.get(c, 0)) for c in company_ids],
                        columns=['company_id', 'current_posts', 'previous_posts', 'delta'])


def competitors(audience, limit=3):
    totals = audience.loc[(audience.platform == 'total') & (audience.role == 'competitor')].dropna(subset=['followers'])
    return totals.sort_values(['followers', 'company_id'], ascending=[False, True]).head(limit)


def key_post(frame, company_id, platform, metric='reactions', minimum_age=0):
    if frame.empty or 'month_end_metric' not in frame:
        return None
    eligible = frame.loc[(frame.company_id == company_id) & (frame.platform == platform) & frame.month_end_metric &
                         (frame.metric_age_days >= minimum_age) & frame[metric].notna()]
    if eligible.empty:
        return None
    return eligible.sort_values([metric, 'published_at', 'post_id'], ascending=[False, True, True]).iloc[0]
