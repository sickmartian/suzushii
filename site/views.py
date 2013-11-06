from pyramid.view import view_config
import requests
import re

from names import Key, NameEntry, NameEntryNames
from kanji import Kanji
from utils import get_database_session, char_is_hiragana, char_is_katakana

class RespondToRequests(object):

    def __init__(self, request):
        self.request = request

    def convert_media_db_model_to_json_model(self, db_entry):

        # Get original name from association
        original_names = db_entry.names.filter(NameEntryNames.language == 'JA')
        for name_entry in original_names:
            original_name = [name_entry.name, \
                             name_entry.name_kana, \
                             name_entry.name_romaji]
            break

        return {
            'kind': db_entry.kind,
            'name': db_entry.common_representation,
            'originalName': original_name,
            'score': float(db_entry.ranking)
        }

    @view_config(renderer="json", name='kanjiMedia')
    def get_kanji_media(self):
        # Get parameters
        print(self.request.subpath)
        kanji = self.request.subpath[0]
        if (not len(self.request.subpath) > 1):
            lookup_kinds = ['Anime']
        else:
            lookup_kinds = [ self.request.subpath[1] ]

        # Get media
        session = get_database_session()
        existing_keys = session.query(NameEntry).join(Key, NameEntry.keys).filter(NameEntry.kind == 'Anime').filter(Key.key_id == kanji)
        media = []
        for entry in existing_keys:
            media.append(self.convert_media_db_model_to_json_model(entry))

        return {
            'kanji': kanji,
            'media': media
        }

    @view_config(renderer="json", name='kanjiDetails')
    def get_details(self):

        kanji_to_get = self.request.subpath[0]
        kanji = Kanji.getKanji(kanji_to_get)

        meanings = []
        for meaning in kanji.meanings:
            meanings.append(meaning.value)

        on_readings = []
        for on_reading in kanji.on_readings:
            on_readings.append(on_reading.value)

        kun_readings = []
        for kun_reading in kanji.kun_readings:
            kun_readings.append(kun_reading.value)

        return {
            'kanji': kanji_to_get,
            'kunyomi': kun_readings,
            'onyomi': on_readings,
            'meaning': meanings
        }
