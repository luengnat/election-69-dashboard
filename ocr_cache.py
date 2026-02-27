#!/usr/bin/env python3
"""
Persistent caching for OCR results.

Uses SQLite to store extracted ballot data keyed by file hash and configuration version.
Prevents redundant processing of the same images.
"""

import sqlite3
import hashlib
import json
import logging
import os
import time
from typing import Optional, Any
from dataclasses import asdict
from contextlib import contextmanager

logger = logging.getLogger(__name__)

from ballot_types import BallotData

class ResultCache:
    """
    SQLite-based cache for OCR results.
    """
    
    DB_PATH = ".serena/cache/ocr_results.db"
    CURRENT_VERSION = "v1.3"  # Bump this to invalidate all cache entries
    
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or self.DB_PATH
        self._init_db()
        
    def _init_db(self):
        """Initialize database schema."""
        dirpath = os.path.dirname(self.db_path)
        if dirpath:
            os.makedirs(dirpath, exist_ok=True)
        
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS results (
                    file_hash TEXT,
                    config_hash TEXT,
                    data_json TEXT,
                    timestamp REAL,
                    PRIMARY KEY (file_hash, config_hash)
                )
            """)
            
    @contextmanager
    def _get_conn(self):
        """Get database connection with auto-close."""
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            # Enable WAL for better concurrency; ignore failures
            try:
                conn.execute("PRAGMA journal_mode=WAL;")
            except Exception:
                pass
            yield conn
        finally:
            conn.close()
            
    def _compute_file_hash(self, file_path: str) -> str:
        """Compute SHA256 hash of file content."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
        
    def get(self, file_path: str) -> Optional[BallotData]:
        """
        Retrieve cached result for a file.
        
        Returns None if not found or config mismatch.
        """
        try:
            file_hash = self._compute_file_hash(file_path)
            
            with self._get_conn() as conn:
                cursor = conn.execute(
                    "SELECT data_json FROM results WHERE file_hash = ? AND config_hash = ?",
                    (file_hash, self.CURRENT_VERSION)
                )
                row = cursor.fetchone()
                
                if row:
                    data_dict = json.loads(row[0])
                    # Reconstruct BallotData from dict (handles nested dataclasses if any)
                    return BallotData.from_dict(data_dict)
                    
        except Exception as e:
            logger.exception("Cache read error")
            
        return None
        
    def set(self, file_path: str, result: BallotData):
        """
        Cache a result.
        """
        try:
            file_hash = self._compute_file_hash(file_path)
            
            # recursive conversion for nested dataclasses
            # assuming BallotData is dataclass
            data_json = json.dumps(asdict(result), ensure_ascii=False)
            
            with self._get_conn() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO results (file_hash, config_hash, data_json, timestamp)
                    VALUES (?, ?, ?, ?)
                    """,
                    (file_hash, self.CURRENT_VERSION, data_json, time.time())
                )
                conn.commit()
                
        except Exception as e:
            logger.exception("Cache write error")

# Global instance
cache = ResultCache()
