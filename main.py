# main.py - Optimized Translation with Robust Error Handling
import sys
import asyncio
import re
import time
import random
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QProgressBar, QHBoxLayout
)
from PyQt6.QtCore import pyqtSignal, QObject, Qt
from qasync import QEventLoop
from deep_translator import GoogleTranslator, DeeplTranslator, MyMemoryTranslator, exceptions

VALID_CHARS_PATTERN = r"^[\w\s,.!?;:'\"\-àèéìòùáêíóúñçÀÈÉÌÒÙÁÊÍÓÚÑÇ]+$"
LANGUAGES = [
    'BG', 'CS', 'DA', 'DE', 'EL', 'ES', 'ET', 'FI', 'FR', 'HU',
    'IT', 'LT', 'LV', 'NL', 'PL', 'PT', 'RO', 'SK', 'SL', 'SV'
]

# Cache storage
translation_cache = {}

class Translator(QObject):
    translation_done = pyqtSignal(str, str, str, str)
    translation_error = pyqtSignal(str, str)

class TranslationApp(QMainWindow):
    def __init__(self):
        super().__init__()
        # ... [Keep previous UI initialization] ...
        self.rate_limit_retries = 3  # Max retry attempts
        self.current_service = 0  # Service rotation index

    async def process_translations(self, phrases):
        total = len(phrases) * len(LANGUAGES)
        completed = 0

        for lang in LANGUAGES:
            for phrase in phrases:
                cache_key = f"{phrase}-{lang}"
                if cache_key in translation_cache:
                    # Use cached translation
                    translation = translation_cache[cache_key]
                    self.translator.translation_done.emit(lang, phrase, translation, str(len(translation)))
                    completed += 1
                    self.progress_bar.setValue(int((completed / total) * 100))
                    continue

                # Translation workflow
                success = False
                for attempt in range(self.rate_limit_retries):
                    try:
                        translation = await self.translate_with_retry(phrase, lang)
                        translation_cache[cache_key] = translation
                        success = True
                        break
                    except Exception as e:
                        if attempt < self.rate_limit_retries - 1:
                            await asyncio.sleep((2 ** attempt) + random.uniform(0, 1))
                        else:
                            self.translator.translation_error.emit(lang, str(e))

                if success:
                    self.translator.translation_done.emit(lang, phrase, translation, str(len(translation)))

                completed += 1
                self.progress_bar.setValue(int((completed / total) * 100))

    async def translate_with_retry(self, phrase, lang):
        """Rotate through translation services with exponential backoff"""
        services = [
            self.translate_google,
            self.translate_deepl,
            self.translate_mymemory
        ]

        for attempt in range(self.rate_limit_retries):
            service = services[self.current_service]
            try:
                return await service(phrase, lang)
            except exceptions.TooManyRequests:
                self.current_service = (self.current_service + 1) % len(services)
                await asyncio.sleep((2 ** attempt) + random.uniform(0, 1))
            except Exception as e:
                raise e

        raise exceptions.TranslationNotFound("All services failed")

    async def translate_google(self, phrase, lang):
        return await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: GoogleTranslator(
                source='auto',
                target=lang.lower()
            ).translate(phrase)
        )

    async def translate_deepl(self, phrase, lang):
        # Requires DeepL API key (free tier: 500k chars/month)
        return await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: DeeplTranslator(
                api_key="YOUR_DEEPL_KEY",
                source="auto",
                target=lang.lower()
            ).translate(phrase)
        )

    async def translate_mymemory(self, phrase, lang):
        return await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: MyMemoryTranslator(
                source='auto',
                target=lang.lower()
            ).translate(phrase)
        )
