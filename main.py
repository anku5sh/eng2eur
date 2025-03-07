# main.py - Final Optimized Version
import sys
import os
import asyncio
import re
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

logging.basicConfig(
    filename=os.path.expanduser("~/eng2eur_debug.log"),
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s: %(message)s'
)

VALID_CHARS_PATTERN = r'^[^\x00-\x1F\x7F]*$'
LANGUAGES = [
    'BG', 'CS', 'DA', 'DE', 'EL', 'ES', 'ET', 'FI', 'FR', 'HU',
    'IT', 'LT', 'LV', 'NL', 'PL', 'PT', 'RO', 'SK', 'SL', 'SV'
]
BASE_DELAY = 0.02  # Further reduced delay
CONCURRENT_TASKS = 10  # Parallel translations
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 600

def get_resource_path(relative_path):
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class Translator(QObject):
    original_ready = pyqtSignal(str, int)
    translation_done = pyqtSignal(str, str, str, int)
    translation_error = pyqtSignal(str, str)

class TranslationApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("eng2eur Translator")
        self.setGeometry(100, 100, WINDOW_WIDTH, WINDOW_HEIGHT)
        self.translator = Translator()
        self._rate_limit_multiplier = 1
        self.global_max_chars = 0
        self.loading_label = QLabel("Loading translations...")
        self.init_db()
        self.init_ui()
        self.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT)

        self.translator.original_ready.connect(
            self.show_original,
            Qt.ConnectionType.QueuedConnection
        )
        self.translator.translation_done.connect(
            self.update_output,
            Qt.ConnectionType.QueuedConnection
        )
        self.translator.translation_error.connect(
            self.show_error,
            Qt.ConnectionType.QueuedConnection
        )

    def init_db(self):
        try:
            db_path = get_resource_path("translations.db")
            self.conn = sqlite3.connect(db_path)
            c = self.conn.cursor()
            c.execute('''
                CREATE TABLE IF NOT EXISTS translations
                (source TEXT, target TEXT, phrase TEXT, translation TEXT,
                UNIQUE(source, target, phrase))
            ''')
            self.conn.commit()
        except Exception as e:
            logging.error(f"Database error: {str(e)}")
            raise

    def get_cached_translation(self, phrase, lang):
        c = self.conn.cursor()
        c.execute('''
            SELECT translation FROM translations
            WHERE source='auto' AND target=? AND phrase=?
        ''', (lang, phrase))
        result = c.fetchone()
        return result[0] if result else None

    def store_translation(self, phrase, translation, lang):
        c = self.conn.cursor()
        c.execute('''
            INSERT OR IGNORE INTO translations
            VALUES (?, ?, ?, ?)
        ''', ('auto', lang, phrase, translation))
        self.conn.commit()

    def init_ui(self):
        central_widget = QWidget()
        main_layout = QVBoxLayout()

        # Loading indicator
        self.loading_label = QLabel("Loading translations...")
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_label.setHidden(True)

        # Input Section
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
        self.output_area.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.output_area.append(f"{'Lang':<5}{'Translation':<65}{'Chars':>6}")
        self.output_area.append("-" * 90)

        main_layout.addWidget(self.loading_label)
        main_layout.addWidget(self.input_label)
        main_layout.addLayout(input_row)
        main_layout.addWidget(self.progress_bar)
        main_layout.addWidget(self.output_area)

        self.translate_btn.clicked.connect(self.start_translation)
        self.input_field.returnPressed.connect(self.start_translation)

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
        self.loading_label.setHidden(False)
        self.translate_btn.setEnabled(False)
        self.output_area.append(f"{'Lang':<5}{'Translation':<65}{'Chars':>6}")
        self.output_area.append("-" * 90)
        self.progress_bar.setValue(0)
        self.global_max_chars = 0

        phrases = [p.strip() for p in text.split(';') if p.strip()]
        asyncio.create_task(self.process_translations(phrases))

    async def process_translations(self, phrases):
        total = len(phrases) * len(LANGUAGES)
        completed = 0
        semaphore = asyncio.Semaphore(CONCURRENT_TASKS)

        async def process_phrase(phrase):
            nonlocal completed
            async with semaphore:
                for lang in LANGUAGES:
                    target_lang = lang.lower()
                    try:
                        cached_translation = self.get_cached_translation(phrase, target_lang)
                        if not cached_translation:
                            translation = await self.translate_phrase(phrase, target_lang)
                            self.store_translation(phrase, translation, target_lang)
                        else:
                            translation = cached_translation

                        char_count = len(translation)
                        self.global_max_chars = max(self.global_max_chars, char_count)
                        self.translator.translation_done.emit(lang, phrase, translation, char_count)
                        completed += 1
                        self.progress_bar.setValue(int((completed / total) * 100))

                    except Exception as e:
                        self.translator.translation_error.emit(lang, str(e))

                    await asyncio.sleep(BASE_DELAY)

        await asyncio.gather(*[process_phrase(phrase) for phrase in phrases])
        self.loading_label.setHidden(True)
        self.translate_btn.setEnabled(True)

    async def translate_phrase(self, phrase, lang):
        services = [GoogleTranslator, MyMemoryTranslator]
        for attempt in range(3):
            try:
                service = services[attempt % len(services)]
                return await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: service(source='auto', target=lang).translate(phrase)
                )
            except exceptions.TooManyRequests:
                delay = (2 ** attempt) + random.uniform(0, 1)
                await asyncio.sleep(delay)
            except Exception as e:
                if attempt == 2:
                    raise e
        raise exceptions.TranslationNotFound("Translation failed after 3 attempts")

    def show_original(self, phrase, char_count):
        self.output_area.append(f"Original: {phrase} ({char_count} characters)\n")

    def update_output(self, lang, original, translation, char_count):
        translation_lines = [
            translation[i:i+65]
            for i in range(0, len(translation), 65)
        ]

        for idx, line in enumerate(translation_lines):
            lang_col = lang if idx == 0 else ""
            char_col = str(char_count) if idx == 0 else ""

            if char_count == self.global_max_chars and idx == 0:
                char_col = f"[{char_col}]"

            formatted_line = f"{lang_col:<5}{line:<65}{char_col:>6}"
            self.output_area.append(formatted_line)

    def show_error(self, context, message):
        self.output_area.append(f"\n[ERROR] {context}: {message}\n")

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
        sys.exit(1) #yay
