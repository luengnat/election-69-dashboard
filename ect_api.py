#!/usr/bin/env python3
"""
ECT (Election Commission of Thailand) API client.

Provides access to official election reference data and statistics.
"""

import json
import urllib.request
from typing import Optional
from dataclasses import dataclass, field
from functools import lru_cache


# ECT API endpoints
ECT_BASE_URL = "https://static-ectreport69.ect.go.th/data/data/refs"
ECT_STATS_URL = "https://stats-ectreport69.ect.go.th/data/records"

ECT_ENDPOINTS = {
    "provinces": f"{ECT_BASE_URL}/info_province.json",
    "constituencies": f"{ECT_BASE_URL}/info_constituency.json",
    "party_overview": f"{ECT_BASE_URL}/info_party_overview.json",
    "mp_candidates": f"{ECT_BASE_URL}/info_mp_candidate.json",
    "party_candidates": f"{ECT_BASE_URL}/info_party_candidate.json",
    "stats_cons": f"{ECT_STATS_URL}/stats_cons.json",
    "stats_party": f"{ECT_STATS_URL}/stats_party.json",
}


@dataclass
class Province:
    """Thai province data."""
    province_id: str
    prov_id: str
    name: str  # Thai name
    abbre_thai: str
    eng: str
    total_vote_stations: int
    total_registered_vote: int


@dataclass
class Party:
    """Political party data."""
    id: str
    party_no: str  # Party number on ballot
    name: str  # Thai name
    abbr: str
    color: str
    logo_url: str


@dataclass
class Constituency:
    """Electoral constituency data."""
    cons_id: str
    cons_no: int
    prov_id: str
    zones: list[str] = field(default_factory=list)
    total_vote_stations: int = 0
    registered_vote: Optional[int] = None


@dataclass
class Candidate:
    """MP candidate data."""
    mp_app_id: str  # Format: {prov_abbr}_{cons_no}_{position}
    mp_app_no: int  # Position number (1, 2, 3...)
    mp_app_party_id: int  # Party ID
    mp_app_name: str  # Thai name
    image_url: str = ""

    @property
    def province_abbr(self) -> str:
        """Extract province abbreviation from ID."""
        parts = self.mp_app_id.split("_")
        return parts[0] if len(parts) > 0 else ""

    @property
    def constituency_no(self) -> int:
        """Extract constituency number from ID."""
        parts = self.mp_app_id.split("_")
        return int(parts[1]) if len(parts) > 1 else 0

    @property
    def position(self) -> int:
        """Extract position from ID."""
        parts = self.mp_app_id.split("_")
        return int(parts[2]) if len(parts) > 2 else self.mp_app_no


@lru_cache(maxsize=1)
def fetch_json(url: str) -> dict:
    """Fetch JSON data from URL with caching."""
    print(f"Fetching: {url}")
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode('utf-8'))


class ECTData:
    """ECT reference data loader and validator."""

    def __init__(self):
        self._provinces: dict[str, Province] = {}
        self._parties: dict[str, Party] = {}
        self._constituencies: dict[str, Constituency] = {}
        self._candidates: dict[str, Candidate] = {}  # Indexed by mp_app_id
        self._candidates_by_position: dict[tuple, Candidate] = {}  # (prov_abbr, cons_no, position)
        self._loaded = False

    def load(self):
        """Load all reference data from ECT APIs."""
        if self._loaded:
            return

        # Load provinces
        prov_data = fetch_json(ECT_ENDPOINTS["provinces"])
        for p in prov_data.get("province", []):
            prov = Province(
                province_id=p["province_id"],
                prov_id=p["prov_id"],
                name=p["province"],
                abbre_thai=p["abbre_thai"],
                eng=p["eng"],
                total_vote_stations=p["total_vote_stations"],
                total_registered_vote=p["total_registered_vote"],
            )
            self._provinces[prov.prov_id] = prov
            self._provinces[prov.name] = prov  # Also index by Thai name

        # Load parties
        party_data = fetch_json(ECT_ENDPOINTS["party_overview"])
        for p in party_data:
            party = Party(
                id=p["id"],
                party_no=p["party_no"],
                name=p["name"],
                abbr=p["abbr"],
                color=p["color"],
                logo_url=p["logo_url"],
            )
            self._parties[party.party_no] = party
            self._parties[party.name] = party  # Also index by Thai name

        # Load constituencies
        cons_data = fetch_json(ECT_ENDPOINTS["constituencies"])
        for c in cons_data:
            cons = Constituency(
                cons_id=c["cons_id"],
                cons_no=c["cons_no"],
                prov_id=c["prov_id"],
                zones=c.get("zone", []),
                total_vote_stations=c.get("total_vote_stations", 0),
                registered_vote=c.get("registered_vote"),
            )
            self._constituencies[cons.cons_id] = cons

        self._loaded = True
        print(f"Loaded {len(self._provinces)//2} provinces, {len(self._parties)//2} parties, {len(self._constituencies)} constituencies")

    def load_candidates(self):
        """Load MP candidate data from ECT API."""
        if self._candidates:
            return  # Already loaded

        # Load MP candidates (constituency)
        cand_data = fetch_json(ECT_ENDPOINTS["mp_candidates"])
        for c in cand_data:
            candidate = Candidate(
                mp_app_id=c["mp_app_id"],
                mp_app_no=c["mp_app_no"],
                mp_app_party_id=c["mp_app_party_id"],
                mp_app_name=c["mp_app_name"],
                image_url=c.get("image_url", ""),
            )
            self._candidates[candidate.mp_app_id] = candidate
            # Also index by position for easy lookup
            key = (candidate.province_abbr, candidate.constituency_no, candidate.position)
            self._candidates_by_position[key] = candidate

        print(f"Loaded {len(self._candidates)} MP candidates")

    def get_province(self, name_or_id: str) -> Optional[Province]:
        """Get province by Thai name or ID."""
        self.load()
        return self._provinces.get(name_or_id)

    def get_party(self, number_or_name: str) -> Optional[Party]:
        """Get party by ballot number or Thai name."""
        self.load()
        return self._parties.get(str(number_or_name))

    def get_constituency(self, cons_id: str) -> Optional[Constituency]:
        """Get constituency by ID."""
        self.load()
        return self._constituencies.get(cons_id)

    def validate_province_name(self, thai_name: str) -> tuple[bool, Optional[str]]:
        """
        Validate a Thai province name.
        Returns (is_valid, canonical_name).
        """
        self.load()
        prov = self._provinces.get(thai_name)
        if prov:
            return True, prov.name
        return False, None

    def get_province_abbr(self, thai_name: str) -> Optional[str]:
        """Get province abbreviation (prov_id) from Thai name."""
        self.load()
        prov = self._provinces.get(thai_name)
        if prov:
            return prov.prov_id
        return None

    def get_party_by_number(self, number: int) -> Optional[Party]:
        """Get party by ballot number."""
        return self.get_party(str(number))

    def list_provinces(self) -> list[str]:
        """List all province names (Thai)."""
        self.load()
        return sorted(set(p.name for p in self._provinces.values() if isinstance(p, Province)))

    def list_parties(self) -> list[tuple[str, str]]:
        """List all parties as (number, name) tuples."""
        self.load()
        return sorted(
            [(p.party_no, p.name) for p in self._parties.values() if isinstance(p, Party)],
            key=lambda x: int(x[0]) if x[0].isdigit() else 999
        )

    def get_candidate(self, mp_app_id: str) -> Optional[Candidate]:
        """Get candidate by application ID."""
        self.load_candidates()
        return self._candidates.get(mp_app_id)

    def get_candidate_by_position(self, province_abbr: str, constituency_no: int, position: int) -> Optional[Candidate]:
        """
        Get candidate by position.

        Args:
            province_abbr: Province abbreviation (e.g., "KBI" for กระบี่)
            constituency_no: Constituency number
            position: Position number (1, 2, 3...)
        """
        self.load_candidates()
        key = (province_abbr.upper(), constituency_no, position)
        return self._candidates_by_position.get(key)

    def get_candidates_for_constituency(self, province_abbr: str, constituency_no: int) -> list[Candidate]:
        """Get all candidates for a specific constituency."""
        self.load_candidates()
        candidates = []
        for key, candidate in self._candidates_by_position.items():
            if key[0] == province_abbr.upper() and key[1] == constituency_no:
                candidates.append(candidate)
        return sorted(candidates, key=lambda c: c.position)

    def get_party_for_candidate(self, candidate: Candidate) -> Optional[Party]:
        """Get the party for a candidate."""
        self.load()
        # Party ID in candidate data maps to party.id (not party_no)
        for party in self._parties.values():
            if isinstance(party, Party) and party.id == str(candidate.mp_app_party_id):
                return party
        return None

    def load_official_results(self):
        """Load official election results from ECT statistics API."""
        if hasattr(self, '_results_loaded') and self._results_loaded:
            return
        
        # Note: ECT stats endpoints return aggregate results
        # This is a placeholder for future implementation
        # when we understand the exact structure of ECT stats data
        self._results_loaded = True
        print("Official results loading placeholder (structure to be determined)")

    def get_official_constituency_results(self, cons_id: str) -> Optional[dict]:
        """
        Get official results for a constituency.
        
        Args:
            cons_id: Constituency ID
            
        Returns:
            Dictionary with official vote counts by candidate position, or None
        """
        # This will be implemented once ECT stats structure is understood
        return None

    def get_official_party_results(self, party_no: int) -> Optional[dict]:
        """
        Get official results for a political party.
        
        Args:
            party_no: Party ballot number
            
        Returns:
            Dictionary with official vote counts by polling station, or None
        """
        # This will be implemented once ECT stats structure is understood
        return None

    def get_candidate_by_thai_province(self, thai_province: str, constituency_no: int, position: int) -> Optional[Candidate]:
        """
        Get candidate by Thai province name, constituency, and position.

        Args:
            thai_province: Province name in Thai (e.g., "แพร่")
            constituency_no: Constituency number
            position: Position number (1, 2, 3...)

        Returns:
            Candidate object or None if not found
        """
        # Get province abbreviation from Thai name
        prov_abbr = self.get_province_abbr(thai_province)
        if not prov_abbr:
            return None
        
        # Lookup candidate by abbreviation
        return self.get_candidate_by_position(prov_abbr, constituency_no, position)

    def get_candidates_by_thai_province(self, thai_province: str, constituency_no: int) -> list[Candidate]:
        """
        Get all candidates for a constituency by Thai province name.

        Args:
            thai_province: Province name in Thai (e.g., "แพร่")
            constituency_no: Constituency number

        Returns:
            List of Candidate objects sorted by position, or empty list if none found
        """
        # Get province abbreviation from Thai name
        prov_abbr = self.get_province_abbr(thai_province)
        if not prov_abbr:
            return []
        
        # Get all candidates for the province/constituency
        return self.get_candidates_for_constituency(prov_abbr, constituency_no)


# Global instance
ect_data = ECTData()


if __name__ == "__main__":
    # Test the API
    ect = ECTData()
    ect.load()

    print("\n=== Sample Provinces ===")
    for name in ect.list_provinces()[:5]:
        prov = ect.get_province(name)
        print(f"  {name} ({prov.eng})")

    print("\n=== Sample Parties ===")
    for no, name in ect.list_parties()[:10]:
        party = ect.get_party(no)
        print(f"  #{no}: {name} ({party.abbr})")

    # Test validation
    print("\n=== Validation Tests ===")
    valid, canonical = ect.validate_province_name("กรุงเทพมหานคร")
    print(f"  'กรุงเทพมหานคร': valid={valid}, canonical={canonical}")

    valid, canonical = ect.validate_province_name("ไม่มีจังหวัดนี้")
    print(f"  'ไม่มีจังหวัดนี้': valid={valid}, canonical={canonical}")
