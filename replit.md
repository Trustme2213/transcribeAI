# Overview

This is a comprehensive web-based audio transcription application with advanced AI-powered speech-to-text capabilities. The system provides automated audio-to-text transcription using OpenAI Whisper with TurboScribe-style enhancements, intelligent audio preprocessing, and a modern web interface for managing transcription tasks. Previously operated as a Telegram bot, now fully transitioned to a web-based interface for better user experience and unlimited message length.

# System Architecture

## Backend Architecture
- **Framework**: Flask web application with PostgreSQL database
- **Bot Framework**: pyTelegramBotAPI for Telegram integration
- **Database**: PostgreSQL with SQLAlchemy ORM for data persistence
- **Audio Processing**: Multi-layered audio processing pipeline with chunking capabilities
- **Transcription**: OpenAI Whisper models with Faster Whisper optimization support
- **AI Integration**: YandexGPT for dialog formatting and analysis

## Frontend Architecture
- **Web Interface**: Modern responsive web UI with Bootstrap dark theme
- **Dashboard**: TurboScribe-style interface with drag-and-drop file upload
- **Admin Panel**: Web-based administration interface for system management
- **Transcription Management**: Individual pages for each transcription with detailed progress tracking

# Key Components

## Audio Processing Pipeline
1. **Audio Chunker** (`audio_chunker.py`): Splits large audio files into manageable chunks with configurable overlap
2. **Audio Preprocessor** (`audio_preprocessor.py`): Applies noise reduction, volume normalization, and format standardization
3. **Audio Analyzer** (`audio_analyzer.py`): Intelligent analysis of audio characteristics for optimal preprocessing parameters
4. **Whisper Transcription** (`whisper_transcription.py`): Multi-model transcription with support for standard and Faster Whisper

## Database Models
- **User**: Telegram user management with authorization system
- **Survey**: Survey/questionnaire definitions for analysis
- **Question**: Individual questions within surveys
- **Inspection**: Instances of survey evaluations
- **Answer**: User responses to survey questions
- **AdminUser**: Administrative user management
- **AuthRequest**: Authorization request tracking

## Web Interface Features
- Drag-and-drop audio file upload with format validation
- Real-time transcription progress tracking
- Modern dashboard with transcription history
- Individual transcription detail pages with metadata
- Download options (TXT, PDF formats)
- Advanced audio preprocessing with TurboScribe-style enhancements
- Copy-to-clipboard functionality

## Queue Management
- **Persistent Queue** (`persistent_queue.py`): Database-backed task queue for reliable audio processing
- **Queue Manager** (`queue_manager.py`): In-memory queue system for real-time processing
- Multi-threaded processing with configurable worker pools

# Data Flow

1. **Audio Input**: Users upload audio files via Telegram bot
2. **Preprocessing**: Audio files are analyzed and preprocessed for optimal quality
3. **Chunking**: Large files are split into smaller segments with overlap
4. **Transcription**: Each chunk is transcribed using Whisper models
5. **Assembly**: Transcription chunks are merged into complete text
6. **AI Processing**: YandexGPT formats dialog and performs analysis
7. **Evaluation**: Content is evaluated against predefined survey questions
8. **Output**: Results are delivered as formatted text and PDF reports

# External Dependencies

## AI Services
- **OpenAI Whisper**: Primary transcription engine
- **Faster Whisper**: Optimized transcription alternative
- **YandexGPT**: Dialog formatting and analysis service

## Audio Processing
- **pydub**: Audio manipulation and format conversion
- **librosa**: Advanced audio analysis and feature extraction
- **scipy**: Signal processing and mathematical operations
- **FFmpeg**: Audio codec support and conversion

## Infrastructure
- **PostgreSQL**: Primary database for data persistence
- **Gunicorn**: WSGI server for Flask application deployment
- **Telegram Bot API**: Bot communication interface

# Deployment Strategy

## Environment Configuration
- Deployment target: Autoscale configuration
- Multi-module Nix environment with Python 3.11 and PostgreSQL 16
- Containerized deployment with Gunicorn WSGI server
- Support for both development and production environments

## Scalability Features
- Database connection pooling with automatic reconnection
- Configurable worker threads for audio processing
- Persistent task queue for handling interruptions
- Modular architecture allowing horizontal scaling

## Monitoring and Logging
- Comprehensive logging system with file and console output
- Error tracking and exception handling
- Performance monitoring for audio processing tasks
- Admin interface for system status and configuration

# Changelog
- June 26, 2025: Major transition to web-based interface
  - Removed Telegram bot dependency for unlimited transcription length
  - Created TurboScribe-style dashboard with drag-and-drop upload
  - Added individual transcription detail pages with progress tracking
  - Implemented download functionality for TXT and PDF formats
  - Integrated all previous audio enhancement features into web UI

- June 23, 2025: Added TurboScribe-style enhancement system
  - Implemented advanced audio preprocessing (adaptive noise reduction, dynamic range compression)
  - Added multi-stage transcription with beam search optimization
  - Integrated intelligent post-processing with error correction and punctuation enhancement
  - Created fallback system with multiple quality levels

# User Preferences

Preferred communication style: Simple, everyday language.
Focus on transcription quality improvements and advanced audio processing techniques.