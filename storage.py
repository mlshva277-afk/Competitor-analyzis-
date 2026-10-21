"""SQLite storage. Demo lives in a separate database selected by the UI."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (Column, Integer, String, Text, Float, ForeignKey,
                        UniqueConstraint, create_engine, event, select)
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


def utcnow():
    return datetime.now(timezone.utc).isoformat()


class Company(Base):
    __tablename__ = 'companies'
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    role = Column(String, nullable=False)


class Account(Base):
    __tablename__ = 'accounts'
    id = Column(Integer, primary_key=True)
    company_id = Column(String, ForeignKey('companies.id'), nullable=False)
    platform = Column(String, nullable=False)
    account_id = Column(String, nullable=False)
    source_url = Column(Text, nullable=False)
    clean_url = Column(Text, nullable=False)
    verification = Column(String, nullable=False)
    collected_at = Column(String, nullable=False, default=utcnow)
    __table_args__ = (UniqueConstraint('platform', 'account_id'),)


class AudienceSnapshot(Base):
    __tablename__ = 'audience_snapshots'
    id = Column(Integer, primary_key=True)
    account_pk = Column(Integer, ForeignKey('accounts.id'), nullable=False)
    observed_at = Column(String, nullable=False)
    collected_at = Column(String, nullable=False, default=utcnow)
    source_url = Column(Text, nullable=False)
    followers = Column(Integer, nullable=False)
    __table_args__ = (UniqueConstraint('account_pk', 'observed_at'),)


class Post(Base):
    __tablename__ = 'posts'
    id = Column(Integer, primary_key=True)
    company_id = Column(String, ForeignKey('companies.id'), nullable=False)
    account_pk = Column(Integer, ForeignKey('accounts.id'), nullable=True)
    platform = Column(String, nullable=False)
    post_id = Column(String, nullable=False)
    source_url = Column(Text, nullable=False)
    published_at = Column(String, nullable=False)
    collected_at = Column(String, nullable=False, default=utcnow)
    text = Column(Text, nullable=False)
    kind = Column(String, nullable=False)  # official / external
    communication_tone = Column(String, nullable=False, default='не определён')
    label_method = Column(String, nullable=False, default='local_rules')
    __table_args__ = (UniqueConstraint('platform', 'post_id', 'company_id', 'kind'),)


class PostMetricSnapshot(Base):
    __tablename__ = 'post_metric_snapshots'
    id = Column(Integer, primary_key=True)
    post_pk = Column(Integer, ForeignKey('posts.id'), nullable=False)
    observed_at = Column(String, nullable=False)
    collected_at = Column(String, nullable=False, default=utcnow)
    source_url = Column(Text, nullable=False)
    reactions = Column(Integer)
    comments_count = Column(Integer)
    shares = Column(Integer)
    views = Column(Integer)
    reach = Column(Integer)
    followers = Column(Integer)  # audience measured at metric observation time
    __table_args__ = (UniqueConstraint('post_pk', 'observed_at'),)


class Comment(Base):
    __tablename__ = 'comments'
    id = Column(Integer, primary_key=True)
    post_pk = Column(Integer, ForeignKey('posts.id'), nullable=False)
    comment_id = Column(String, nullable=False)
    text = Column(Text, nullable=False)
    source_url = Column(Text, nullable=False)
    collected_at = Column(String, nullable=False, default=utcnow)
    issuer_tone = Column(String, nullable=False)
    market_tone = Column(String, nullable=False)
    question_topic = Column(String)
    analysis_method = Column(String, nullable=False, default='manual_or_unknown')
    __table_args__ = (UniqueConstraint('post_pk', 'comment_id'),)


class TopicLabel(Base):
    __tablename__ = 'topic_labels'
    id = Column(Integer, primary_key=True)
    post_pk = Column(Integer, ForeignKey('posts.id'), nullable=False)
    category = Column(String, nullable=False)  # topic / format
    label = Column(String, nullable=False)
    __table_args__ = (UniqueConstraint('post_pk', 'category', 'label'),)


class SourceSyncRun(Base):
    __tablename__ = 'source_sync_runs'
    id = Column(Integer, primary_key=True)
    source = Column(String, nullable=False)
    platform = Column(String, nullable=False)
    account_pk = Column(Integer, ForeignKey('accounts.id'))
    collected_at = Column(String, nullable=False, default=utcnow)
    status = Column(String, nullable=False)
    rows_count = Column(Integer, nullable=False, default=0)
    error = Column(Text)
    coverage = Column(Text, nullable=False)


def database(path=None):
    path = Path(path or os.getenv('ISI_DB_PATH', 'data/invest.sqlite')).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine('sqlite:///' + str(path), connect_args={'check_same_thread': False})
    @event.listens_for(engine, 'connect')
    def foreign_keys(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    return engine, sessionmaker(engine, expire_on_commit=False)


def seed_registry(factory, path='data/accounts.json'):
    registry = json.loads(Path(path).read_text(encoding='utf-8'))
    sources = registry['sources']
    if len(sources) != 15 or len({s['company_id'] for s in sources}) != 10:
        raise ValueError('Ожидается реестр 10 компаний / 15 аккаунтов')
    with factory.begin() as session:
        for item in sources:
            company = session.get(Company, item['company_id'])
            if company is None:
                session.add(Company(id=item['company_id'], name=item['company'], role=item['role']))
                session.flush()
            account = session.scalar(select(Account).where(Account.platform == item['platform'], Account.account_id == item['account_id']))
            if account is None:
                session.add(Account(**{k: item[k] for k in ('company_id', 'platform', 'account_id', 'source_url', 'clean_url', 'verification')}))
    return registry
