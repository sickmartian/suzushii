from sqlalchemy import Column, Integer, String, Numeric
from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship, backref
import requests
import re

from utils import Base, get_database_session
from utils import char_is_hiragana, char_is_katakana

class Kanji(Base):
    """
        Kanji
    """
    __tablename__ = 'kanji'

    kanji_id = Column(String, primary_key=True)
    on_readings = relationship('OnReading')
    kun_readings = relationship('KunReading')
    meanings = relationship('Meaning')

    def __init__(self, kanji):
        self.kanji_id = kanji

    @classmethod
    def getKanji(cls, kanji):
        session = get_database_session()

        existing_kanjis = session.query(Kanji).filter(Kanji.kanji_id==kanji)
        for existing_kanji in existing_kanjis:
            print('Found {0}'.format(existing_kanji.kanji_id))
            return existing_kanji

        new_kanji = Kanji(kanji)
        new_kanji.update_related_data(session)

        return new_kanji

    def update_related_data(self, existing_session=None):
        search_string = '1ZMJ' # Search by UTF-8 Kanji

        req = requests.get('http://www.csse.monash.edu.au/~jwb/cgi-bin/wwwjdic.cgi?{0}{1}'.format(search_string, self.kanji_id))
        print('Requesting {0} got me: {1}'.format(self.kanji_id, req.text))

        content_regexp = re.compile(r'<pre>(.*?)<\/pre>', re.DOTALL | re.MULTILINE)
        content = content_regexp.search(req.text).group(1)
        words = content.split(' ')

        # From this service, onyomi is in katakana and kunyomi is in hiragana
        # separate the readings
        kunyomi = []
        onyomi = []
        for word in words:
            word_is_hiragana = True
            word_is_katakana = True
            for char in word:
                if not char_is_hiragana(char):
                    word_is_hiragana = False
                if not char_is_katakana(char):
                    word_is_katakana = False
                if word_is_katakana == False or word_is_katakana == False:
                    break
            if word_is_hiragana:
                kunyomi.append(word)
            if word_is_katakana:
                onyomi.append(word)

        # We get the meanings wraped in {}
        meanings = []
        meaning_regexp = re.compile(r'{(.*?)}')
        meanings = meaning_regexp.findall(req.text)

        if (existing_session):
            db_s = existing_session
        else:
            db_s = get_database_session()

        db_s.add(self)
        for i, meaning in enumerate(meanings):
            m = Meaning(i, meaning)
            self.meanings.append(m)

        for i, on in enumerate(onyomi):
            o = OnReading(i, on)
            self.on_readings.append(o)

        for i, kun in enumerate(kunyomi):
            k = KunReading(i, kun)
            self.kun_readings.append(k)

        self.update_self(db_s)

    def __repr__(self):
        return self.kanji_id

class OnReading(Base):
    """
        On reading of a kanji
    """
    __tablename__ = 'onreadings'

    kanji_id = Column(String, ForeignKey('kanji.kanji_id'), primary_key=True)
    sub_id = Column(Integer, primary_key=True)
    value = Column(String)

    def __init__(self, i, value):
        self.sub_id = i
        self.value = value

class KunReading(Base):
    """
        On reading of a kanji
    """
    __tablename__ = 'kunreadings'

    kanji_id = Column(String, ForeignKey('kanji.kanji_id'), primary_key=True)
    sub_id = Column(Integer, primary_key=True)
    value = Column(String)

    def __init__(self, i, value):
        self.sub_id = i
        self.value = value

class Meaning(Base):
    """
        On reading of a kanji
    """
    __tablename__ = 'kanji_meanings'

    kanji_id = Column(String, ForeignKey('kanji.kanji_id'), primary_key=True)
    sub_id = Column(Integer, primary_key=True)
    value = Column(String)

    def __init__(self, i, value):
        self.sub_id = i
        self.value = value

if __name__ == "__main__":
    from multiprocessing import Pool

    # kanjis = [(chr(kan_code)) for kan_code in set(range(21056, 21157))] <-- Known for testing
    kanjis = [(chr(kan_code)) for kan_code in set(range(19968, 40864)) | set(range(13312, 19903))]

    pool = Pool()
    for k in kanjis:
        pool.apply_async(Kanji.getKanji, args=(k, ))

    pool.close()
    pool.join()
