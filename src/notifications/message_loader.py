#!/usr/bin/env python3
"""
Multi-language message loader for Discord notifications
Based on JSON locale files with random message selection
"""

import json
import random
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime


class MessageLoader:
    """Load and manage multi-language messages from external JSON files"""
    
    def __init__(self, locales_dir: str = None, default_language: str = "ko"):
        """
        Initialize message loader
        
        Args:
            locales_dir: Directory containing language JSON files
            default_language: Default language code (fallback)
        """
        if locales_dir is None:
            # Auto-detect locales directory relative to this file
            locales_dir = Path(__file__).parent / "locales"
        
        self.locales_dir = Path(locales_dir)
        self.default_language = default_language
        self.loaded_languages: Dict[str, Dict] = {}
        
        # Validate locales directory exists
        if not self.locales_dir.exists():
            raise FileNotFoundError(f"Locales directory not found: {self.locales_dir}")
    
    def _load_language(self, language_code: str) -> Dict[str, Any]:
        """Load language file into memory"""
        language_file = self.locales_dir / f"{language_code}.json"
        
        # Fallback to default language if file doesn't exist
        if not language_file.exists():
            if language_code != self.default_language:
                return self._load_language(self.default_language)
            else:
                raise FileNotFoundError(f"Default language file not found: {language_file}")
        
        try:
            with open(language_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            if language_code != self.default_language:
                # Fallback to default language on error
                return self._load_language(self.default_language)
            else:
                raise RuntimeError(f"Failed to load default language file: {e}")
    
    def get_message(
        self, 
        message_path: str, 
        language: str = None, 
        **format_kwargs
    ) -> str:
        """
        Get localized message with random variation support
        
        Args:
            message_path: Dot-separated path to message (e.g., "server.start")
            language: Language code (uses default if None)
            **format_kwargs: Arguments for string formatting
            
        Returns:
            Formatted localized message
        """
        lang = language or self.default_language
        
        # Load language if not already loaded
        if lang not in self.loaded_languages:
            self.loaded_languages[lang] = self._load_language(lang)
        
        # Navigate to message using dot-separated path
        message_data = self.loaded_languages[lang]
        path_parts = message_path.split('.')
        
        try:
            for part in path_parts:
                message_data = message_data[part]
        except (KeyError, TypeError):
            # Fallback to default language
            if lang != self.default_language:
                return self.get_message(message_path, self.default_language, **format_kwargs)
            else:
                return f"Message not found: {message_path}"
        
        # Handle list of message variations (random selection)
        if isinstance(message_data, list):
            message = random.choice(message_data)
        else:
            message = message_data
        
        # Format message with provided arguments
        try:
            return message.format(**format_kwargs)
        except (KeyError, ValueError):
            # Return unformatted message if formatting fails
            return message
    
    def get_status_message(self, player_count: int, language: str = None) -> str:
        """Get player count status message"""
        if player_count == 1:
            return self.get_message("status.alone", language)
        elif player_count <= 5:
            return self.get_message("status.few", language, count=player_count)
        else:
            return self.get_message("status.many", language, count=player_count)
    
    def get_greeting(self, language: str = None) -> str:
        """Get time-based greeting message"""
        current_hour = datetime.now().hour
        
        if 6 <= current_hour < 12:
            return self.get_message("greeting.morning", language)
        elif 12 <= current_hour < 18:
            return self.get_message("greeting.afternoon", language)
        elif 18 <= current_hour < 22:
            return self.get_message("greeting.evening", language)
        else:
            return self.get_message("greeting.night", language)
    
    def get_available_languages(self) -> List[str]:
        """Get list of available language codes"""
        if not self.locales_dir.exists():
            return []
        
        languages = []
        for file_path in self.locales_dir.glob("*.json"):
            languages.append(file_path.stem)
        
        return sorted(languages)
    
    def reload_language(self, language_code: str) -> bool:
        """Reload specific language from disk"""
        try:
            self.loaded_languages[language_code] = self._load_language(language_code)
            return True
        except (FileNotFoundError, RuntimeError):
            return False
    
    def reload_all_languages(self) -> None:
        """Reload all loaded languages from disk"""
        for lang_code in list(self.loaded_languages.keys()):
            self.reload_language(lang_code)


# Global message loader instance
_message_loader: Optional[MessageLoader] = None


def get_message_loader(locales_dir: str = None, default_language: str = "ko") -> MessageLoader:
    """Get global message loader instance (singleton pattern)"""
    global _message_loader
    
    if _message_loader is None:
        _message_loader = MessageLoader(locales_dir, default_language)
    
    return _message_loader
