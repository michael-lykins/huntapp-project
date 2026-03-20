"""
OnX Maps API client.

REST API:  https://api.production.onxmaps.com
GraphQL:   https://api.production.onxmaps.com/v1/supergraph/
Auth:      Bearer {access_token} from OnxAuth
"""
import logging
from typing import Any

import requests

from .onx_auth import OnxAuth

logger = logging.getLogger(__name__)

BASE_URL = "https://api.production.onxmaps.com"

# GraphQL query for land areas (property boundaries)
_LAND_AREAS_QUERY = """
query LandAreas($sort: LandAreaSort) {
  landAreas(sort: $sort) {
    area
    createdAt
    createdBy
    geometry
    id
    name
    sections {
      area
      attributes { countyNames states { abbreviation } }
      geometry
      id
      name
      representativePoint
    }
    style { lineColor fillColor lineStyle lineWeight }
    collection { id }
    userSettings { autoAddUserContent }
    permissions
  }
}
"""

# GraphQL query for trail cameras registered in OnX
_TRAIL_CAMS_QUERY = """
query GetAllTrailCams($first: Int, $after: String) {
  me {
    trailcamsConnection(first: $first, after: $after) {
      edges {
        node {
          id
          name
          inField
          currentPlacement {
            id
            name
            location { lat lon }
            placedAt
            orientation { beginning end }
          }
          deviceInformation {
            make { brand model }
            batteryInformation { numberOfBatteries }
            isCellular
          }
          lastChangedBatteries
          notes { content createdAt updatedAt }
          presentation { color }
          historicalPlacements {
            id name
            location { lat lon }
            placedAt removedAt
            orientation { beginning end }
          }
          removedFromInventoryAt
          sdCard { capacity replacedAt }
          integrationInformation { partnerBrand }
          photos(first: 1, sortBy: {timestampSort: CAPTURED_AT_LOCAL_UPLOADED_AT_DESC}) {
            edges {
              node { contentUrl id capturedAtLocal }
            }
          }
        }
        cursor
      }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""


class OnxClient:
    def __init__(self, auth: OnxAuth):
        self._auth = auth
        self._session = requests.Session()

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._auth.get_token()}",
            "Content-Type": "application/json",
        }

    def _get(self, path: str, params: dict | None = None) -> Any:
        resp = self._session.get(
            f"{BASE_URL}{path}",
            headers=self._headers(),
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    def _graphql(self, query: str, variables: dict | None = None) -> dict:
        resp = self._session.post(
            f"{BASE_URL}/v1/supergraph/",
            headers=self._headers(),
            json={"query": query, "variables": variables or {}},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Markups (REST)
    # ------------------------------------------------------------------

    def get_waypoints(self, limit: int = 500) -> list[dict]:
        data = self._get("/v1/markups/waypoints", {"limit": limit})
        items = data if isinstance(data, list) else data.get("items", [])
        logger.info("Fetched %d waypoints from OnX", len(items))
        return items

    def get_tracks(self, limit: int = 200) -> list[dict]:
        data = self._get("/v1/markups/tracks", {"limit": limit})
        items = data if isinstance(data, list) else data.get("items", [])
        logger.info("Fetched %d tracks from OnX", len(items))
        return items

    def get_lines(self, limit: int = 200) -> list[dict]:
        data = self._get("/v1/markups/lines", {"limit": limit})
        items = data if isinstance(data, list) else data.get("items", [])
        logger.info("Fetched %d lines from OnX", len(items))
        return items

    def get_shapes(self, limit: int = 500) -> list[dict]:
        data = self._get("/v1/markups/shapes", {"limit": limit})
        items = data if isinstance(data, list) else data.get("items", [])
        logger.info("Fetched %d shapes from OnX", len(items))
        return items

    # ------------------------------------------------------------------
    # Land areas + cameras (GraphQL)
    # ------------------------------------------------------------------

    def get_land_areas(self) -> list[dict]:
        result = self._graphql(_LAND_AREAS_QUERY)
        areas = (result.get("data") or {}).get("landAreas", [])
        logger.info("Fetched %d land areas from OnX", len(areas))
        return areas

    def get_trail_cams(self, page_size: int = 50) -> list[dict]:
        cams = []
        cursor = None
        while True:
            variables: dict = {"first": page_size}
            if cursor:
                variables["after"] = cursor
            result = self._graphql(_TRAIL_CAMS_QUERY, variables)
            connection = (
                (result.get("data") or {})
                .get("me", {})
                .get("trailcamsConnection", {})
            )
            edges = connection.get("edges", [])
            cams.extend(e["node"] for e in edges if "node" in e)
            page_info = connection.get("pageInfo", {})
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")
        logger.info("Fetched %d trail cameras from OnX", len(cams))
        return cams
