"""
    Jobs: Can be called to update the series
        or get new ones periodically
"""
import logging
from multiprocessing import Pool

import requests
from lxml import etree
from sqlalchemy import create_engine, and_
from sqlalchemy.orm import sessionmaker

from names import NameEntry, NameEntryNames, Key
from utils import get_database_session, char_is_kanji

class SeriesDetails:
    """
        Iterable that returns a serie's details from ANN
    """

    # Request configuration
    from_serie = 0
    to_serie = 0
    load_step = 0

    # Request control
    request_at = 0
    next_request_at = 0
    last_request_result = []
    cache = []

    # Iterator control
    iterator_at = 0

    def handle_error(self, result):
        logging.error('handle_error at iterator_at: %s request_at: %s', \
            self.iterator_at, \
            self.request_at)

    def get_result(self, result):
        self.last_request_result = etree.fromstring(result).findall('anime')
        self.request_at = self.next_request_at

    @classmethod
    def request_data(cls, from_index, to_index):
        logging.info('Requesting: %s %s', from_index, to_index)

        how_many = to_index - from_index

        # Get list
        list_request_url = 'http://www.animenewsnetwork.com/encyclopedia/reports.xml?id=155&type=anime&nlist={1}&nskip={0}'.format(from_index,
            how_many)
        logging.info('List Url: %s', list_request_url)
        req = requests.get(list_request_url)

        # Get details
        items = etree.fromstring(req.text).findall('item');
        id_string = '/'.join([item.findall('id')[0].text for item in items])
        detail_request_url = 'http://cdn.animenewsnetwork.com/encyclopedia/api.xml?title={0}'.format(id_string)
        logging.info('Details Url: %s', detail_request_url)
        req = requests.get(detail_request_url)

        return req.text

    def request_next(self):
        next_to = self.request_at + self.load_step
        if next_to > self.to_serie:
            next_to = self.to_serie

        request_at = self.request_at
        self.pool.apply_async(SeriesDetails.request_data, \
            args=(request_at, next_to), \
            callback=self.get_result, \
            error_callback=self.handle_error)

        self.next_request_at = next_to

    def __init__(self, from_serie, to_serie, load_step = 50):
        self.from_serie = from_serie
        self.to_serie = to_serie
        self.load_step = load_step

        self.request_at = self.from_serie

        self.pool = Pool(1)

        self.request_next()

    def __iter__(self):
        return self

    def wait_for_worker(self):
        self.pool.close()
        self.pool.join()

    def __next__(self):

        logging.info('In __next__ asking for %s', self.iterator_at)

        if self.iterator_at+self.from_serie > self.to_serie:
            self.wait_for_worker()
            raise StopIteration

        # If the current list is expended, get/wait for next result
        if self.iterator_at % self.load_step == 0:
            logging.info('In __next__ Joining result')
            self.wait_for_worker()
            self.cache = self.last_request_result
            self.pool = Pool(1)

        # Start getting the next result in the middle
        # of the current list
        if (self.iterator_at%self.load_step == self.load_step//2) and \
           (self.request_at < self.to_serie):
            self.request_next()

        logging.info('Asking as: %s rat: %s le: %s ts: %s', \
            self.iterator_at%self.load_step, self.request_at, \
            self.load_step, \
            self.to_serie)

        # Get the result from the series cache,
        # if we can we assume there are no more series for us
        try:
            result = self.cache[self.iterator_at % self.load_step]
        except Exception:
            logging.info('Stopped at Iterator: %s', self.iterator_at)
            self.wait_for_worker()
            raise StopIteration

        self.iterator_at += 1

        return result


class Jobs:
    """
        Method/Function class to update data for the model
    """

    @classmethod
    def get_all_series(cls):
        """
            Gets updated data of all series
        """
        # last one 2013-11-02: 6788, 6789: Angel Links
        # The service gives me back up to 50 at a time

        # Error at: 5500, 6800 o 5350
        return SeriesDetails(0, 6789, 50)

    @classmethod
    def build_series_db(cls):
        """
            Gets all series from the source
            and builds/updates their names and keys (tags/kanjis).
            If they don't have a rating, it tries to get one too
        """

        session = get_database_session()

        # Get series
        series = Jobs.get_all_series()

        # Workers for updating rankings
        pool = Pool()

        # Parse series data
        for serie in series:
            serie_id = int(serie.attrib['id'])
            keys = set()
            names_for_keys = set()
            logging.info('Processing serie id: %s', serie_id)
            for info in serie.findall('info'):
                # Get Kanjis in title
                if info.attrib['type'] == 'Alternative title':
                    if info.attrib['lang'] == 'JA':
                        current_title_keys = set([char for char in info.text \
                            if char_is_kanji(char)])
                        if (current_title_keys):
                            keys = keys | current_title_keys
                            names_for_keys.add(info.text)

                # Get title
                if info.attrib['type'] == 'Main title':
                    main_title = info.text

            # Create serie entry if it doesn't exist
            current_serie = None
            series_found = session.query(NameEntry).filter( \
                and_(NameEntry.entry_id==serie_id, NameEntry.kind=='Anime'))
            for found_serie in series_found:
                current_serie = found_serie
                break
            if current_serie is None:
                current_serie = NameEntry(serie_id, 'Anime', main_title)

            # Create/Update titles
            # Remove names we already have, and create remaining ones
            for existing_name_entry in current_serie.names:
                if existing_name_entry.name in names_for_keys and \
                   existing_name_entry.language == 'JA':
                    names_for_keys.remove(existing_name_entry.name)
            for new_name in names_for_keys:
                current_serie.names.append(NameEntryNames(language='JA',name=new_name))

            # Associate keys/Kanjis
            serie_keys = []
            for key in keys:
                existing_keys = session.query(Key).filter(Key.key_id==key)

                key_to_append = None
                for existing_key in existing_keys:
                    key_to_append = existing_key
                    break
                if not key_to_append:
                    key_to_append = Key(key, key)
                current_serie.keys.append(key_to_append)
                serie_keys.append(key_to_append)

            # Get it into the DB
            session.add(current_serie)
            session.add_all(serie_keys)
            session.commit()

            # Get the ranking
            current_serie.prepare_for_concurrent_operations(session)
            pool.apply_async(current_serie.update_related_data)

        pool.close()
        pool.join()

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    JOBS = Jobs()
    JOBS.build_series_db()
