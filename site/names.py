"""
    Model for the application, here we have
    'NameEntry' that represents the concept to be tagged by 'Key's
    the 'NameEntry' might have multiple representations, which are
    stored in 'NameEntryNames's
"""
from sqlalchemy import Column, Integer, String, Numeric
from sqlalchemy import ForeignKey, ForeignKeyConstraint, Table
from sqlalchemy import and_
from sqlalchemy.orm import relationship, backref
import requests

from lxml import etree, html
from difflib import get_close_matches
import logging
import re

from utils import Base, get_database_session

ENTRY_KEYS = Table('entry_keys', Base.metadata,
    Column('name_entry_id', Integer),
    Column('name_entry_kind', String),
    Column('key_id', String, ForeignKey('keys.key_id')),
    ForeignKeyConstraint(
        ('name_entry_id', 'name_entry_kind'),
        ('name_entries.entry_id', 'name_entries.kind')
    ))

class Key(Base):
    """
        Tag for NameEntry
    """
    __tablename__ = 'keys'

    key_id = Column(String, primary_key=True)
    common_representation = Column(String)

    def __init__(self, key_id, common_representation):
        self.key_id = key_id
        self.common_representation = common_representation

    def __repr__(self):
        return self.common_representation


class NameEntryNames(Base):
    """
        Possible names for NameEntry
    """
    __tablename__ = 'name_entry_names'

    name_id = Column(Integer, primary_key=True)
    entry_id = Column(Integer)
    kind = Column(String)

    language = Column(String)
    name = Column(String)

    name_kana = Column(String)
    name_romaji = Column(String)

    __table_args__ = (
        ForeignKeyConstraint(('entry_id', 'kind'),
            ('name_entries.entry_id','name_entries.kind'))
        ,)

    def update_related_names(self):
        """
            Gets the romaji and kana representations
            and stores them to the db
            NOTE: The object should be detached
                [session.expunge(object)] and all its
                properties available session.refresh(object)
                See prepare_for_concurrent_operations
        """
        req = requests.post('http://romaji.me/romaji.cgi',
            data={
                'mode': 2,
                'hiragana': 1,
                'unknown_text': self.name,
                'text': self.name
            })

        romaji_regexp = re.compile(r'<rt>(.*?)<\/rt>', re.DOTALL | re.MULTILINE)
        self.name_romaji = ' '.join([r for r in romaji_regexp.findall(req.text) if r != ' '])
        print(self.name_romaji)

        kana_regexp = re.compile(r'<rb>(.*?)<\/rb>', re.DOTALL | re.MULTILINE)
        self.name_kana = ' '.join([k for k in kana_regexp.findall(req.text) if k != ' '])
        print(self.name_kana)

        self.update_self()


class NameEntry(Base):
    """
        Object to be tagged/inspected
    """
    __tablename__ = 'name_entries'

    entry_id = Column(Integer, primary_key=True)
    kind = Column(String, primary_key=True)
    common_representation = Column(String)
    ranking = Column(Numeric(precision=5, scale=2), default=-1)

    keys = relationship('Key', secondary=ENTRY_KEYS, backref='entries')
    names = relationship('NameEntryNames', backref=backref('entry'), lazy='dynamic')

    def __init__(self, entry_id, kind, common_representation):
        self.entry_id = entry_id
        self.kind = kind
        self.common_representation = common_representation

    def __repr__(self):
        return self.common_representation

    def update_ranking(self):
        """
            Gets the ranking for this entry and updates
            the DB.
            NOTE: The object should be detached
                [session.expunge(object)] and all its
                properties available session.refresh(object)
                See prepare_for_concurrent_operations
        """
        search_name = self.common_representation
        logging.info('Looking up ranking for: %s', search_name)
        names_found = {}
        series_names = []

        try:
            from configuration import mal_credentials
            req = requests.get('http://myanimelist.net/api/anime/search.xml?q={0}'.format(search_name), \
                               auth=(mal_credentials['username'], mal_credentials['password']))
        except Exception as e:
            logging.error('Error when getting data for: %s', search_name)
            return
        if not req.status_code == requests.codes.ok:
            return

        # Take out first line since etree doesn't support it
        # (b/c of the encoding)
        data = req.text.partition('\n')[2]

        entries = html.fromstring(data).findall('entry')
        if (entries is None):
            return

        # Get list of names and choose the closest one
        for index, entry in enumerate(entries):
            title = entry.findall('title')[0].text
            names_found[title] = index
            series_names.append(title)

        closest_matches = get_close_matches(search_name, series_names, 1)
        if (closest_matches.count == 0):
            closest_match = closest_matches[0]
        else:
            closest_match = series_names[0]
        choosen_entry = entries[names_found[closest_match]]

        # Update the whole object
        from decimal import Decimal
        self.ranking = Decimal(choosen_entry.findall('score')[0].text)
        logging.info('Updating %s with %s', search_name, self.ranking)
        self.update_self()

    def update_related_data(self):
        # Update ourselves first
        self.update_ranking()

        # Get DB session to be able to access the lazy
        # loaded properties, and update our child entities too
        db_s = get_database_session()
        db_s.add(self)
        original_names = self.names.filter(NameEntryNames.language == 'JA')
        for name_entry in original_names:
            name_entry.prepare_for_concurrent_operations(db_s)
            name_entry.update_related_names()

if __name__ == "__main__":

    logging.basicConfig(level=logging.DEBUG)

    session = get_database_session()

# Update series
    series_found = session.query(NameEntry).filter( \
                    and_(NameEntry.kind=='Anime', \
                        NameEntry.common_representation=='Naruto'))

    for serie in series_found:
        serie.prepare_for_concurrent_operations(session)
        serie.update_related_data()

    session.close()

# Update all Names
    # from multiprocessing import Pool

    # pool = Pool()

    # names = session.query(NameEntryNames).filter(NameEntryNames.language == 'JA')
    # for name in names:
    #     print(name.name)
    #     name.prepare_for_concurrent_operations(session)
    #     pool.apply_async(name.update_related_names)

    # pool.close()
    # pool.join()
