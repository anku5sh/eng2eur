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
from PyQt6.QtGui import QTextCursor
from qasync import QEventLoop
from deep_translator import GoogleTranslator, MyMemoryTranslator, exceptions

logging.basicConfig(
    filename=os.path.expanduser("~/eng2eur_debug.log"),
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s: %(message)s'
)

VALID_CHARS_PATTERN = r'^[^\x00-\x1F\x7F]*$'
LANGUAGES = [
    'BG', 'CS', 'DA', 'DE', 'ES', 'ET', 'FI', 'FR', 'HR', 'HU',
    'IT', 'LT', 'LV', 'NL', 'NO', 'PL', 'PT', 'RO',
    'SK', 'SL', 'SV', 'UK'
]
LANG_NAMES = {
    'BG': 'Bulgarian', 'CS': 'Czech', 'DA': 'Danish', 'DE': 'German',
    'ES': 'Spanish', 'ET': 'Estonian', 'FI': 'Finnish', 'FR': 'French',
    'HR': 'Croatian', 'HU': 'Hungarian', 'IT': 'Italian',
    'LT': 'Lithuanian', 'LV': 'Latvian', 'NL': 'Dutch',
    'NO': 'Norwegian', 'PL': 'Polish', 'PT': 'Portuguese', 'RO': 'Romanian',
    'SK': 'Slovak', 'SL': 'Slovenian', 'SV': 'Swedish', 'UK': 'Ukrainian'
}
BASE_DELAY = 0.01
MAX_LINE_LENGTH = 60
LANG_COL_WIDTH = 20
TRANS_COL_WIDTH = 60
CHARS_COL_WIDTH = 10
WINDOW_WIDTH = 900
WINDOW_HEIGHT = 700
MAX_CONCURRENT = 5

def get_resource_path(relative_path):
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def wrap_text(text, max_length):
    """Wrap text at word boundaries, not breaking words"""
    words = text.split()
    lines = []
    current_line = []
    current_length = 0

    for word in words:
        # If adding this word would exceed the limit
        if current_length + len(word) + (1 if current_length > 0 else 0) > max_length:
            # Add the current line to lines and start a new line
            if current_line:
                lines.append(' '.join(current_line))
            current_line = [word]
            current_length = len(word)
        else:
            # Add the word to the current line
            current_line.append(word)
            # Add 1 for the space if not the first word
            current_length += len(word) + (1 if current_length > 0 else 0)

    # Add the last line
    if current_line:
        lines.append(' '.join(current_line))

    return lines

class Translator(QObject):
    original_ready = pyqtSignal(str, int)
    translation_done = pyqtSignal(str, str, str, int)
    translation_error = pyqtSignal(str, str)
    loading_status = pyqtSignal(bool, str)
    progress_update = pyqtSignal(int)

class TranslationApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("eng2eur Translator")
        self.setGeometry(100, 100, WINDOW_WIDTH, WINDOW_HEIGHT)
        self.translator = Translator()
        self._rate_limit_multiplier = 1
        self.translations_buffer = []
        self.global_max_chars = 0
        self.translation_history = []  # Store history of translations
        self.is_first_translation = True  # Flag for first translation
        self.init_db()
        self.init_ui()
        self.setMinimumSize(800, 600)

        self.translator.original_ready.connect(self.show_original)
        self.translator.translation_done.connect(self.update_output)
        self.translator.translation_error.connect(self.show_error)
        self.translator.loading_status.connect(self.update_loading_status)
        self.translator.progress_update.connect(self.progress_bar.setValue)

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

    def get_cached_translations(self, phrases, langs):
        results = {}
        c = self.conn.cursor()
        for phrase in phrases:
            for lang in langs:
                c.execute('''
                    SELECT translation FROM translations
                    WHERE source='auto' AND target=? AND phrase=?
                ''', (lang.lower(), phrase))
                result = c.fetchone()
                if result:
                    key = (phrase, lang.lower())
                    results[key] = result[0]
        return results

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

        self.loading_label = QLabel("Loading, please wait...")
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_label.setStyleSheet("font-weight: bold; color: blue;")
        self.loading_label.setVisible(False)

        self.output_area = QTextEdit()
        self.output_area.setReadOnly(True)
        self.output_area.setFontFamily("Courier New")
        self.output_area.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)

        # Only add header on initialization if it's the first run
        header_format = f"{'Language':<{LANG_COL_WIDTH}}{'Translation':<{TRANS_COL_WIDTH}}{'Chars':>{CHARS_COL_WIDTH}}"
        self.output_area.append(header_format)
        self.output_area.append("-" * (LANG_COL_WIDTH + TRANS_COL_WIDTH + CHARS_COL_WIDTH))

        main_layout.addWidget(self.input_label)
        main_layout.addLayout(input_row)
        main_layout.addWidget(self.progress_bar)
        main_layout.addWidget(self.loading_label)
        main_layout.addWidget(self.output_area)

        self.translate_btn.clicked.connect(self.start_translation)
        self.input_field.returnPressed.connect(self.start_translation)

        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

    def update_loading_status(self, is_loading, message="Loading, please wait..."):
        self.loading_label.setText(message)
        self.loading_label.setVisible(is_loading)
        self.translate_btn.setEnabled(not is_loading)
        self.input_field.setEnabled(not is_loading)

    def start_translation(self):
        text = self.input_field.text().strip()
        if not text:
            self.show_error("Input", "Please enter text to translate")
            return

        if not re.match(VALID_CHARS_PATTERN, text):
            self.show_error("Input", "Invalid control characters detected")
            return

        self.input_field.clear()

        # Add separator between translations but don't clear previous ones
        if not self.is_first_translation:
            self.output_area.append("\n\n" + "=" * (LANG_COL_WIDTH + TRANS_COL_WIDTH + CHARS_COL_WIDTH) + "\n")
            header_format = f"{'Language':<{LANG_COL_WIDTH}}{'Translation':<{TRANS_COL_WIDTH}}{'Chars':>{CHARS_COL_WIDTH}}"
            self.output_area.append(header_format)
            self.output_area.append("-" * (LANG_COL_WIDTH + TRANS_COL_WIDTH + CHARS_COL_WIDTH))
        else:
            # First translation - don't add duplicate headers
            self.is_first_translation = False

        self.progress_bar.setValue(0)
        self.translations_buffer = []
        self.global_max_chars = 0

        phrases = [p.strip() for p in text.split(';') if p.strip()]
        asyncio.create_task(self.process_translations(phrases))

    async def process_translations(self, phrases):
        self.translator.loading_status.emit(True, "Loading, please wait...")

        total = len(phrases) * len(LANGUAGES)
        completed = 0

        # Pre-check cache
        cached_translations = self.get_cached_translations(phrases, [lang.lower() for lang in LANGUAGES])

        for phrase in phrases:
            self.translator.original_ready.emit(phrase, len(phrase))
            phrase_translations = []

            # Process languages in parallel for speed
            tasks = []
            for lang in LANGUAGES:
                target_lang = lang.lower()
                key = (phrase, target_lang)

                if key in cached_translations:
                    translation = cached_translations[key]
                    char_count = len(translation)
                    phrase_translations.append((lang, translation, char_count))
                    self.global_max_chars = max(self.global_max_chars, char_count)
                    completed += 1
                    self.translator.progress_update.emit(int((completed / total) * 100))
                else:
                    tasks.append(self.translate_and_store(phrase, lang, target_lang))

            # Execute translations in batches
            for i in range(0, len(tasks), MAX_CONCURRENT):
                batch = tasks[i:i+MAX_CONCURRENT]
                if batch:
                    results = await asyncio.gather(*batch, return_exceptions=True)
                    for result in results:
                        if not isinstance(result, Exception) and result:
                            lang, translation, char_count = result
                            phrase_translations.append((lang, translation, char_count))
                            self.global_max_chars = max(self.global_max_chars, char_count)
                            completed += 1
                            self.translator.progress_update.emit(int((completed / total) * 100))

                # Small delay between batches to prevent rate limiting
                await asyncio.sleep(BASE_DELAY)

            # Sort translations by language code for consistent display
            phrase_translations.sort(key=lambda x: x[0])

            # Display translations for this phrase
            for lang, translation, char_count in phrase_translations:
                self.translator.translation_done.emit(lang, phrase, translation, char_count)

            # Add to history
            self.translation_history.append((phrase, phrase_translations))

        self.translator.loading_status.emit(False, "")

    async def translate_and_store(self, phrase, lang, target_lang):
        try:
            translation = await self.translate_phrase(phrase, target_lang)
            self.store_translation(phrase, translation, target_lang)

            char_count = len(translation)
            return (lang, translation, char_count)
        except Exception as e:
            self.translator.translation_error.emit(lang, str(e))
            return None

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
        # Wrap text at word boundaries
        original_lines = wrap_text(phrase, MAX_LINE_LENGTH)

        # Display the original phrase with proper wrapping
        if original_lines:
            # Format first line with "Original:" and character count
            first_line = original_lines[0]
            # Format with consistent column widths and proper alignment
            self.output_area.append(f"{'Original:':<{LANG_COL_WIDTH}}{first_line:<{TRANS_COL_WIDTH}}{char_count:>{CHARS_COL_WIDTH}}")

            # Additional lines if the phrase is long
            for line in original_lines[1:]:
                self.output_area.append(f"{'':<{LANG_COL_WIDTH}}{line:<{TRANS_COL_WIDTH}}")

        self.output_area.append("")

        # Scroll to the bottom
        cursor = self.output_area.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.output_area.setTextCursor(cursor)

    def update_output(self, lang, original, translation, char_count):
        lang_name = f"{lang} - {LANG_NAMES.get(lang, 'Unknown')}"
        # Wrap translation at word boundaries
        translation_lines = wrap_text(translation, MAX_LINE_LENGTH)

        for idx, line in enumerate(translation_lines):
            lang_col = lang_name if idx == 0 else ""

            # Only show character count on first line
            if idx == 0:
                if char_count == self.global_max_chars:
                    # Handle max character count with brackets
                    bracketed_count = f"[{char_count}]"
                    # Right-align within the character column
                    char_col = f"{bracketed_count:>{CHARS_COL_WIDTH}}"
                else:
                    char_col = f"{char_count:>{CHARS_COL_WIDTH}}"
            else:
                char_col = ""

            # Format with exact column widths
            formatted_line = f"{lang_col:<{LANG_COL_WIDTH}}{line:<{TRANS_COL_WIDTH}}{char_col}"
            self.output_area.append(formatted_line)

        # Scroll to the bottom
        cursor = self.output_area.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.output_area.setTextCursor(cursor)

    def show_error(self, context, message):
        self.output_area.append(f"\n[ERROR] {context}: {message}\n")
        # Scroll to the bottom
        cursor = self.output_area.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.output_area.setTextCursor(cursor)

if __name__ == "__main__":
    try:
        app = QApplication(sys.argv)
        loop = QEventLoop(app)
        asyncio.set_event_loop(loop)
        window = TranslationApp()
        window.show()
        with loop:
            loop.run_forever()
    except Exception as e:
        logging.critical(f"Fatal error: {str(e)}", exc_info=True)
        sys.exit(1)
