# main.py - Final Functional Version
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
BATCH_SIZE = 5
MAX_RETRIES = 3

class Translator(QObject):
    translation_done = pyqtSignal(str, str, str, str)  # (lang, original, translation, chars)
    translation_error = pyqtSignal(str, str)  # (lang, error)

class TranslationApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("eng2eur Translator")
        self.setGeometry(100, 100, 800, 600)
        self.translator = Translator()
        self.init_db()
        self.init_ui()
        self.setFixedSize(800, 600)
        self.service_index = 0

    def init_db(self):
        self.conn = sqlite3.connect('translations.db')
        c = self.conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS translations
                     (source TEXT, target TEXT, phrase TEXT, translation TEXT,
                      UNIQUE(source, target, phrase))''')
        self.conn.commit()

    def init_ui(self):
        central_widget = QWidget()
        main_layout = QVBoxLayout()

        # Input Section
        self.input_label = QLabel("Enter phrases (semicolon-separated - max 300 chars):")

        # Input row
        input_row = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setMaxLength(300)
        self.input_field.setPlaceholderText("Example: Hello; Goodbye")

        self.translate_btn = QPushButton("Translate")
        self.translate_btn.setFixedWidth(120)

        input_row.addWidget(self.input_field)
        input_row.addWidget(self.translate_btn, alignment=Qt.AlignmentFlag.AlignRight)

        # Progress and Output
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)

        self.output_area = QTextEdit()
        self.output_area.setReadOnly(True)
        self.output_area.setFontFamily("Courier New")
        self.output_area.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.output_area.append(f"{'Lang':<5}{'Translation':<60}{'Chars':>6}")
        self.output_area.append("-" * 80)

        # Assemble layout
        main_layout.addWidget(self.input_label)
        main_layout.addLayout(input_row)
        main_layout.addWidget(self.progress_bar)
        main_layout.addWidget(self.output_area)

        # Connections
        self.translate_btn.clicked.connect(self.start_translation)
        self.input_field.returnPressed.connect(self.start_translation)
        self.translator.translation_done.connect(self.update_output)
        self.translator.translation_error.connect(self.show_error)

        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

    def start_translation(self):
        text = self.input_field.text().strip()

        # Validation
        if not text:
            self.show_error("Input", "Please enter text to translate")
            return

        if len(text) > 300:
            self.show_error("Input", "Maximum 300 characters allowed")
            return

        if not re.match(VALID_CHARS_PATTERN, text):
            invalid = set(re.findall(r"[^\w\s,.!?;:'\"\-àèéìòùáêíóúñçÀÈÉÌÒÙÁÊÍÓÚÑÇ]", text))
            self.show_error("Input", f"Invalid characters: {', '.join(invalid)}")
            return

        self.input_field.clear()
        self.output_area.clear()
        self.output_area.append(f"{'Lang':<5}{'Translation':<60}{'Chars':>6}")
        self.output_area.append("-" * 80)
        self.progress_bar.setValue(0)

        phrases = [p.strip() for p in text.split(';') if p.strip()]
        asyncio.create_task(self.process_translations(phrases))

    async def process_translations(self, phrases):
        total = len(phrases) * len(LANGUAGES)
        completed = 0

        for lang in LANGUAGES:
            for i in range(0, len(phrases), BATCH_SIZE):
                batch = phrases[i:i+BATCH_SIZE]
                success = False

                for attempt in range(MAX_RETRIES):
                    try:
                        translated = await self.translate_batch(batch, lang)
                        self.store_translations(batch, translated, lang)
                        success = True
                        break
                    except exceptions.TooManyRequests:
                        delay = (2 ** attempt) + random.uniform(0, 1)
                        await asyncio.sleep(delay)
                    except Exception as e:
                        self.show_error(lang, str(e))
                        break

                if not success:
                    translated = ["Translation failed"] * len(batch)

                # Update progress
                for phrase, translation in zip(batch, translated):
                    self.translator.translation_done.emit(lang, phrase, translation, str(len(translation)))
                    completed += 1
                    self.progress_bar.setValue(int((completed / total) * 100))

    async def translate_batch(self, phrases, lang):
        """Translate with service rotation and fallback"""
        services = [
            GoogleTranslator,
            lambda: MyMemoryTranslator(source='auto', target=lang.lower()),
            # DeeplTranslator(api_key="YOUR_KEY", source="auto", target=lang.lower())  # Uncomment with API key
        ]

        for service_idx, service in enumerate(services):
            try:
                return await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: service().translate_batch(phrases)
                )
            except Exception as e:
                if service_idx == len(services) - 1:
                    raise e
                await asyncio.sleep(1)

        raise exceptions.TranslationNotFound("All services failed")

    def store_translations(self, phrases, translations, lang):
        c = self.conn.cursor()
        data = [('auto', lang.lower(), p, t) for p, t in zip(phrases, translations)]
        c.executemany('INSERT OR IGNORE INTO translations VALUES (?,?,?,?)', data)
        self.conn.commit()

    def update_output(self, lang, original, translation, char_count):
        line = f"{lang:<5}{translation[:60]:<60}{char_count:>6}"
        self.output_area.append(line)

    def show_error(self, context, message):
        self.output_area.append(f"\nERROR [{context}]: {message}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    window = TranslationApp()
    window.show()

    with loop:
        sys.exit(loop.run_forever())
