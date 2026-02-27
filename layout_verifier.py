#!/usr/bin/env python3
"""
Layout Verification using Vision Language Models (VLM).

Performs a structural sanity check on ballot images before detailed extraction.
Useful for confirming page numbers, form types, and rejecting non-ballot images.
"""

import os
import json
import base64
import requests
from typing import Optional, Dict, Any
from dataclasses import dataclass

@dataclass
class LayoutAnalysis:
    is_ballot: bool
    page_number: int
    form_type_code: Optional[str]  # e.g., "5/18"
    is_party_list: bool
    has_vote_table: bool
    confidence: float

class LayoutVerifier:
    """
    Uses a VLM to analyze document structure.
    """
    
    DEFAULT_MODEL = "google/gemma-3-12b-it:free"
    BASE_URL = "https://openrouter.ai/api/v1"
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        
    @property
    def is_available(self) -> bool:
        return bool(self.api_key)
        
    def verify(self, image_path: str) -> Optional[LayoutAnalysis]:
        """
        Analyze the image structure.
        """
        if not self.is_available:
            return None
            
        try:
            with open(image_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")
                
            prompt = """Analyze this document structure.
            1. Is it a Thai election ballot tally form (marked with Garuda emblem/Thai text)?
            2. Look for page number (e.g. "Page 1 of 2"). Default to 1 if not found.
            3. Look for form code (e.g. "ส.ส. 5/18").
            4. Is it Party-List (has "บัญชีรายชื่อ" or "(บช)")?
            5. Does it have a vote count table?
            
            Return ONLY valid JSON:
            {
                "is_ballot": true/false,
                "page_number": int,
                "form_code": "string" or null,
                "is_party_list": true/false,
                "has_vote_table": true/false,
                "confidence": 0.0-1.0
            }"""
            
            response = requests.post(
                url=f"{self.BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/election-verification",
                    "X-Title": "Thai Election Layout Verifier",
                },
                json={
                    "model": self.DEFAULT_MODEL,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_data}"}},
                            {"type": "text", "text": prompt},
                        ],
                    }],
                    "max_tokens": 512,
                },
                timeout=30,
            )
            
            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                # Strip markdown
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]
                    
                data = json.loads(content.strip())
                
                return LayoutAnalysis(
                    is_ballot=data.get("is_ballot", False),
                    page_number=data.get("page_number", 1),
                    form_type_code=data.get("form_code"),
                    is_party_list=data.get("is_party_list", False),
                    has_vote_table=data.get("has_vote_table", False),
                    confidence=data.get("confidence", 0.5)
                )
                
        except Exception as e:
            print(f"  Layout verification failed: {e}")
            
        return None

# Global instance
verifier = LayoutVerifier()
