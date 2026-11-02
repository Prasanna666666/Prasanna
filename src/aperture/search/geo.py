"""Offline reverse geocoding from the GeoNames ``cities15000`` list.

Turns EXIF GPS coordinates into "Bengaluru, India" with no network access,
and keeps alternate names ("Bangalore") so that natural-language place
queries match.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..config import Paths
from .textnorm import fold, index_text

EARTH_KM = 6371.0


@dataclass(frozen=True)
class Place:
    name: str
    country: str
    search_text: str  # folded names + alternates + country, for LIKE matching
    distance_km: float

    @property
    def label(self) -> str:
        return f"{self.name}, {self.country}" if self.country else self.name


class GeoIndex:
    def __init__(
        self,
        names: list[str],
        countries: list[str],
        search: list[str],
        lat: np.ndarray,
        lon: np.ndarray,
        population: np.ndarray | None = None,
    ) -> None:
        self._names, self._countries, self._search = names, countries, search
        self._pop = population if population is not None else np.zeros(len(names))
        self._lat = np.radians(lat.astype(np.float64))
        self._lon = np.radians(lon.astype(np.float64))
        self._cos_lat = np.cos(self._lat)

    def __len__(self) -> int:
        return len(self._names)

    @classmethod
    def load(cls, paths: Paths) -> GeoIndex | None:
        """``None`` when the data files have not been fetched (feature degrades)."""
        cities, country_file = paths.geo / "cities15000.txt", paths.geo / "countryInfo.txt"
        if not cities.exists():
            return None
        return cls.from_files(cities, country_file if country_file.exists() else None)

    @classmethod
    def from_files(cls, cities: Path, country_info: Path | None) -> GeoIndex:
        country_names: dict[str, str] = {}
        if country_info is not None:
            for line in country_info.read_text(encoding="utf-8", errors="replace").splitlines():
                if line and not line.startswith("#"):
                    cols = line.split("\t")
                    if len(cols) > 4:
                        country_names[cols[0]] = cols[4]
        names, countries, search, lats, lons, pops = [], [], [], [], [], []
        for line in cities.read_text(encoding="utf-8", errors="replace").splitlines():
            cols = line.split("\t")
            if len(cols) < 9:
                continue
            try:
                lat, lon = float(cols[4]), float(cols[5])
            except ValueError:
                continue
            country = country_names.get(cols[8], cols[8])
            alternates = [a for a in cols[3].split(",") if a and len(a) <= 24]
            variants = {cols[1], cols[2], *alternates[:40]}
            names.append(cols[1])
            countries.append(country)
            search.append(index_text(*sorted(variants), country, cols[8]))
            lats.append(lat)
            lons.append(lon)
            try:
                pops.append(float(cols[14]))
            except (IndexError, ValueError):
                pops.append(0.0)
        return cls(names, countries, search, np.array(lats), np.array(lons), np.array(pops))

    def lookup(self, lat: float, lon: float, max_km: float = 80.0) -> Place | None:
        """Nearest listed city within ``max_km`` (haversine), else ``None``."""
        if not (-90 <= lat <= 90 and -180 <= lon <= 180) or not len(self):
            return None
        lat_r, lon_r = math.radians(lat), math.radians(lon)
        dlat = self._lat - lat_r
        dlon = (self._lon - lon_r + math.pi) % (2 * math.pi) - math.pi
        a = np.sin(dlat / 2) ** 2 + self._cos_lat * math.cos(lat_r) * np.sin(dlon / 2) ** 2
        dist = 2 * EARTH_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
        i = int(dist.argmin())
        if dist[i] > max_km:
            return None
        return Place(self._names[i], self._countries[i], self._search[i], float(dist[i]))

    def find(self, name: str) -> tuple[float, float, str] | None:
        """Coordinates of the best-known place called ``name`` (largest city wins), or ``None``."""
        wanted = fold(name)
        if not wanted:
            return None
        exact = [i for i, n in enumerate(self._names) if fold(n) == wanted]
        pool = exact or [i for i, text in enumerate(self._search) if f" {wanted}" in text]
        if not pool:
            return None
        best = max(pool, key=lambda i: self._pop[i])
        return (
            float(np.degrees(self._lat[best])),
            float(np.degrees(self._lon[best])),
            f"{self._names[best]}, {self._countries[best]}",
        )
