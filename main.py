# main.py - Final Version with Fallback & Validation
import sys
import asyncio
import re
import time
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QProgressBar, QHBoxLayout
)
from PyQt6.QtCore import pyqtSignal, QObject, Qt
from qasync import QEventLoop
from deep_translator import GoogleTranslator, MyMemoryTranslator, exceptions

# Allowed characters: letters, numbers, basic punctuation, and accents
VALID_CHARS_PATTERN = r"^[\w\s,.!?;:'\"\-àèéìòùáêíóúñçÀÈÉÌÒÙÁÊÍÓÚÑÇ]+$"
LANGUAGES = [
    'BG', 'CS', 'DA', 'DE', 'EL', 'ES', 'ET', 'FI', 'FR', 'HU',
    'IT', 'LT', 'LV', 'NL', 'PL', 'PT', 'RO', 'SK', 'SL', 'SV'
]

class Translator(QObject):
    translation_done = pyqtSignal(str, str, str, str)  # (lang, original, translation, char_count)
    translation_error = pyqtSignal(str, str)  # (lang, error_msg)

class TranslationApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("eng2eur Translator")
        self.setGeometry(100, 100, 800, 600)
        self.translator = Translator()
        self.init_ui()
        self.setFixedSize(800, 600)
        self.last_request_time = 0

    def init_ui(self):
        central_widget = QWidget()
        main_layout = QVBoxLayout()

        # Input Section
        self.input_label = QLabel("Enter phrases (semicolon-separated - max 300 chars):")

        # Input row with button
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
        self.output_area.append(f"{'Lang':<5}{'Translation':<65}{'Chars':>6}")
        self.output_area.append("-" * 90)

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

        # Input Validation
        if not text:
            self.show_error("Input", "Please enter text to translate")
            return

        if len(text) > 300:
            self.show_error("Input", "Maximum 300 characters allowed")
            return

        if not re.match(VALID_CHARS_PATTERN, text):
            invalid_chars = set(re.findall(r"[^\w\s,.!?;:'\"\-àèéìòùáêíóúñçÀÈÉÌÒÙÁÊÍÓÚÑÇ]", text))
            self.show_error("Input", f"Invalid characters: {', '.join(invalid_chars)}")
            return

        self.input_field.clear()
        self.output_area.clear()
        self.output_area.append(f"{'Lang':<5}{'Translation':<65}{'Chars':>6}")
        self.output_area.append("-" * 90)
        self.progress_bar.setValue(0)

        phrases = [p.strip() for p in text.split(';') if p.strip()]
        asyncio.create_task(self.process_translations(phrases))

    async def process_translations(self, phrases):
        total = len(phrases) * len(LANGUAGES)
        completed = 0

        for lang in LANGUAGES:
            # Rate limit: 1 request per second per language
            while time.time() - self.last_request_time < 1:
                await asyncio.sleep(0.1)

            try:
                # First try Google Translate
                translated_batch = await self.translate_batch(phrases, lang, GoogleTranslator)
            except Exception as google_error:
                try:
                    # Fallback to MyMemory
                    translated_batch = await self.translate_batch(phrases, lang, MyMemoryTranslator)
                except Exception as memory_error:
                    translated_batch = [f"Translation failed: {str(memory_error)}"] * len(phrases)

            for phrase, translation in zip(phrases, translated_batch):
                char_count = str(len(translation))
                self.translator.translation_done.emit(lang, phrase, translation, char_count)
                completed += 1
                self.progress_bar.setValue(int((completed / total) * 100))

            self.last_request_time = time.time()

    async def translate_batch(self, phrases, lang, translator_class):
        return await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: translator_class(
                source='auto',
                target=lang.lower()
            ).translate_batch(phrases)
        )

    def update_output(self, lang, original, translation, char_count):
        line = f"{lang:<5}{translation[:65]:<65}{char_count:>6}"
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
