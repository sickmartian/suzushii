from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

BaseBase = declarative_base()

class Base(BaseBase):
    __abstract__ = True

    def prepare_for_concurrent_operations(self, session):
        session.refresh(self)
        session.expunge(self)

    def update_self(self, existing_session=None):
        """
            Updates the object (if it's detached,
                it uses a new session)
        """
        if (not existing_session):
            session = get_database_session()
        else:
            session = existing_session

        session.add(self)
        session.commit()

        if (not existing_session):
            session.expunge(self)

def get_database_session():
    engine = create_engine('sqlite:///db.db', echo=False)
    Base.metadata.create_all(engine)
    session_maker = sessionmaker(bind=engine)
    return session_maker()

def char_is_kanji(char):
    return ( (19968 < ord(char) < 40864) or \
             (13312 < ord(char) < 19903) )

def char_is_hiragana(char):
    return ( (12288 < ord(char) < 12351) or \
             (12352 < ord(char) < 12447) )

def char_is_katakana(char):
    return ( (12288 < ord(char) < 12351) or \
             (12448 < ord(char) < 12543) )
