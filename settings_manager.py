"""
Settings manager for audio preprocessing system.
Handles getting current settings from database and providing defaults.
"""

import json
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

class SettingsManager:
    """
    Manages system settings for audio preprocessing.
    """
    
    def __init__(self):
        self._cache = {}
        self._cache_valid = False
    
    def get_setting(self, key: str, default_value: Any = None) -> Any:
        """Get a system setting value with caching."""
        if not self._cache_valid:
            self._refresh_cache()
        
        return self._cache.get(key, default_value)
    
    def _refresh_cache(self):
        """Refresh settings cache from database."""
        try:
            # Import here to avoid circular imports
            from main import SystemSettings, app
            
            # Ensure we're in application context
            with app.app_context():
                settings = SystemSettings.query.all()
                self._cache = {}
                
                for setting in settings:
                    try:
                        # Try to parse JSON for complex values
                        value = json.loads(setting.setting_value)
                    except (json.JSONDecodeError, TypeError):
                        value = setting.setting_value
                    
                    self._cache[setting.setting_key] = value
                
                self._cache_valid = True
                logger.debug(f"Refreshed settings cache with {len(self._cache)} settings")
            
        except Exception as e:
            logger.warning(f"Failed to refresh settings cache: {e}")
            # Use defaults if database is not available
            self._cache = self._get_default_settings()
            self._cache_valid = True
    
    def _get_default_settings(self) -> Dict[str, Any]:
        """Get default settings if database is not available."""
        return {
            'audio_preprocessing_enabled': True,
            'chunk_size_ms': 180000,
            'overlap_ms': 2000,
            'noise_reduction_enabled': True,
            'volume_normalization_enabled': True,
            'compression_enabled': True,
            'speech_optimization_enabled': True
        }
    
    def invalidate_cache(self):
        """Invalidate the settings cache to force refresh on next access."""
        self._cache_valid = False
    
    def get_audio_processing_config(self) -> Dict[str, Any]:
        """Get complete audio processing configuration."""
        return {
            'enabled': self.get_setting('audio_preprocessing_enabled', True),
            'chunk_size_ms': self.get_setting('chunk_size_ms', 180000),
            'overlap_ms': self.get_setting('overlap_ms', 2000),
            'noise_reduction': self.get_setting('noise_reduction_enabled', True),
            'volume_normalization': self.get_setting('volume_normalization_enabled', True),
            'compression': self.get_setting('compression_enabled', True),
            'speech_optimization': self.get_setting('speech_optimization_enabled', True)
        }

# Global settings manager instance
settings_manager = SettingsManager()