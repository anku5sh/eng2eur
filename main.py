# main.py - Optimized Translation Engine
import sys
import asyncio
import re
import time
import random
import sqlite3
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QProgressBar, QHBoxLayout
)
from PyQt6.QtCore import pyqtSignal, QObject, Qt
from qasync import QEventLoop
from deep_translator import GoogleTranslator, MyMemoryTranslator, DeeplTranslator, exceptions

# Configuration
VALID_CHARS_PATTERN = r"^[\w\s,.!?;:'\"\-àèéìòùáêíóúñçÀÈÉÌÒÙÁÊÍÓÚÑÇ]+$"
LANGUAGES = [
    'BG', 'CS', 'DA', 'DE', 'EL', 'ES', 'ET', 'FI', 'FR', 'HU',
    'IT', 'LT', 'LV', 'NL', 'PL', 'PT', 'RO', 'SK', 'SL', 'SV'
]
BATCH_SIZE = 10  # Requests per service call
SERVICES = [GoogleTranslator, MyMemoryTranslator]  # Add DeeplTranslator with API key

class Translator(QObject):
    translation_done = pyqtSignal(str, str, str, str)
    translation_error = pyqtSignal(str, str)

class TranslationApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("eng2eur Translator")
        self.setGeometry(100, 100, 800, 600)
        self.translator = Translator()
        self.init_ui()
        self.setFixedSize(800, 600)
        self.service_index = 0
        self.init_db()

    def init_db(self):
        self.conn = sqlite3.connect('translations.db')
        c = self.conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS translations
                     (source text, target text, phrase text, translation text)''')
        self.conn.commit()

    def init_ui(self):
        # ... [Keep previous UI initialization code] ...

    async def process_translations(self, phrases):
        total = len(phrases) * len(LANGUAGES)
        completed = 0

        for lang in LANGUAGES:
            # Batch processing
            for i in range(0, len(phrases), BATCH_SIZE):
                batch = phrases[i:i+BATCH_SIZE]
                success = False

                for attempt in range(3):  # Retry loop
                    service = SERVICES[self.service_index % len(SERVICES)]
                    self.service_index += 1

                    try:
                        translated = await self.translate_batch(batch, lang, service)
                        self.store_translations(batch, translated, lang)
                        success = True
                        break
                    except exceptions.TooManyRequests:
                        await asyncio.sleep((2 ** attempt) + random.uniform(0, 1))
                    except Exception as e:
                        self.translator.translation_error.emit(lang, str(e))
                        break

                if not success:
                    translated = ["Translation failed"] * len(batch)

                # Emit results
                for phrase, translation in zip(batch, translated):
                    self.translator.translation_done.emit(
                        lang, phrase, translation, str(len(translation))
                    )
                    completed += 1
                    self.progress_bar.setValue(int((completed / total) * 100))

    async def translate_batch(self, phrases, lang, translator):
        """Batch translation with service rotation"""
        cached = self.get_cached_translations(phrases, lang)
        if len(cached) == len(phrases):
            return [t[0] for t in cached]

        return await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: translator(
                source='auto',
                target=lang.lower()
            ).translate_batch(phrases)
        )

    def get_cached_translations(self, phrases, lang):
        c = self.conn.cursor()
        placeholders = ','.join(['?']*len(phrases))
        c.execute(f'''SELECT translation FROM translations
                    WHERE source='auto' AND target=? AND phrase IN ({placeholders})''',
                  [lang.lower()] + phrases)
        return c.fetchall()

    def store_translations(self, phrases, translations, lang):
        c = self.conn.cursor()
        data = [('auto', lang.lower(), p, t) for p, t in zip(phrases, translations)]
        c.executemany('INSERT OR IGNORE INTO translations VALUES (?,?,?,?)', data)
        self.conn.commit()

    # ... [Keep other methods unchanged] ...

if __name__ == "__main__":
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    window = TranslationApp()
    window.show()

    with loop:
        sys.exit(loop.run_forever())
