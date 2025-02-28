# main.py - Version 2.0 with Original Phrase Display
import sys
import os
import asyncio
import re
import time
import random
import sqlite3
import logging
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QProgressBar, QHBoxLayout
)
from PyQt6.QtCore import pyqtSignal, QObject, Qt
from qasync import QEventLoop
from deep_translator import GoogleTranslator, MyMemoryTranslator, exceptions

# Configure logging
logging.basicConfig(
    filename=os.path.expanduser("~/eng2eur_debug.log"),
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s: %(message)s'
)

# Configuration
VALID_CHARS_PATTERN = r'^[^\x00-\x1F\x7F]*$'
LANGUAGES = [
    'BG', 'CS', 'DA', 'DE', 'EL', 'ES', 'ET', 'FI', 'FR', 'HU',
    'IT', 'LT', 'LV', 'NL', 'PL', 'PT', 'RO', 'SK', 'SL', 'SV'
]
BATCH_SIZE = 3

def get_resource_path(relative_path):
    """Get absolute path to resource for dev and PyInstaller"""
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class Translator(QObject):
    original_ready = pyqtSignal(str, int)  # (phrase, char_count)
    translation_done = pyqtSignal(str, str, str, int)  # (lang, original, translation, char_count)
    translation_error = pyqtSignal(str, str)

class TranslationApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("eng2eur Translator")
        self.setGeometry(100, 100, 800, 600)
        self.translator = Translator()
        self.init_db()
        self.init_ui()
        self.setFixedSize(800, 600)
        logging.info("Application initialized")

    def init_db(self):
        try:
            db_path = get_resource_path("translations.db")
            self.conn = sqlite3.connect(db_path)
            c = self.conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS translations
                        (source TEXT, target TEXT, phrase TEXT, translation TEXT,
                        UNIQUE(source, target, phrase))''')
            self.conn.commit()
            logging.info("Database initialized")
        except Exception as e:
            logging.error(f"Database error: {str(e)}")
            raise

    def init_ui(self):
        central_widget = QWidget()
        main_layout = QVBoxLayout()

        self.input_label = QLabel("Enter phrases (semicolon-separated):")

        input_row = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setMaxLength(500)
        self.input_field.setPlaceholderText("Example: Hello; Goodbye")

        self.translate_btn = QPushButton("Translate")
        self.translate_btn.setFixedWidth(120)

        input_row.addWidget(self.input_field)
        input_row.addWidget(self.translate_btn, alignment=Qt.AlignmentFlag.AlignRight)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)

        self.output_area = QTextEdit()
        self.output_area.setReadOnly(True)
        self.output_area.setFontFamily("Courier New")
        self.output_area.append(f"{'Original':<20}{'Language':<8}{'Translation':<50}{'Chars':>6}")
        self.output_area.append("-" * 90)

        main_layout.addWidget(self.input_label)
        main_layout.addLayout(input_row)
        main_layout.addWidget(self.progress_bar)
        main_layout.addWidget(self.output_area)

        self.translate_btn.clicked.connect(self.start_translation)
        self.input_field.returnPressed.connect(self.start_translation)
        self.translator.original_ready.connect(self.show_original)
        self.translator.translation_done.connect(self.update_output)
        self.translator.translation_error.connect(self.show_error)

        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

    def start_translation(self):
        text = self.input_field.text().strip()
        if not text:
            self.show_error("Input", "Please enter text to translate")
            return

        if not re.match(VALID_CHARS_PATTERN, text):
            self.show_error("Input", "Invalid control characters detected")
            return

        self.input_field.clear()
        self.output_area.clear()
        self.output_area.append(f"{'Original':<20}{'Language':<8}{'Translation':<50}{'Chars':>6}")
        self.output_area.append("-" * 90)
        self.progress_bar.setValue(0)

        phrases = [p.strip() for p in text.split(';') if p.strip()]
        asyncio.create_task(self.process_translations(phrases))

    async def process_translations(self, phrases):
        total = len(phrases) * len(LANGUAGES)
        completed = 0

        for phrase in phrases:
            # Show original phrase first
            self.translator.original_ready.emit(phrase, len(phrase))

            # Process translations for each language
            for lang in LANGUAGES:
                try:
                    translated = await self.translate_phrase(phrase, lang.lower())
                    self.store_translation(phrase, translated, lang.lower())
                    self.translator.translation_done.emit(lang, phrase, translated, len(translated))
                except Exception as e:
                    self.translator.translation_error.emit(lang, str(e))

                completed += 1
                self.progress_bar.setValue(int((completed / total) * 100))
                await asyncio.sleep(0.3)  # Rate limiting

    async def translate_phrase(self, phrase, lang):
        """Translate with service rotation and retry logic"""
        services = [GoogleTranslator, MyMemoryTranslator]
        for attempt in range(3):
            try:
                service = services[attempt % len(services)]
                return await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: service(source='auto', target=lang).translate(phrase)
                )
            except exceptions.TooManyRequests:
                await asyncio.sleep((2 ** attempt) + random.uniform(0, 1))
            except Exception as e:
                if attempt == 2:
                    raise e
        raise exceptions.TranslationNotFound("Translation failed after 3 attempts")

    def store_translation(self, phrase, translation, lang):
        c = self.conn.cursor()
        c.execute('INSERT OR IGNORE INTO translations VALUES (?,?,?,?)',
                  ('auto', lang, phrase, translation))
        self.conn.commit()

    def show_original(self, phrase, char_count):
        self.output_area.append(f"{phrase:<20}{'Original':<8}{'':<50}{char_count:>6}")

    def update_output(self, lang, original, translation, char_count):
        line = f"{'':<20}{lang:<8}{translation[:50]:<50}{char_count:>6}"
        self.output_area.append(line)

    def show_error(self, context, message):
        self.output_area.append(f"\n{'ERROR':<20}{context:<8}{message[:50]:<50}{'':>6}")

if __name__ == "__main__":
    try:
        app = QApplication(sys.argv)
        loop = QEventLoop(app)
        asyncio.set_event_loop(loop)

        window = TranslationApp()
        window.show()

        with loop:
            sys.exit(loop.run_forever())
    except Exception as e:
        logging.critical(f"Fatal error: {str(e)}", exc_info=True)
        sys.exit(1)
