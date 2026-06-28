import asyncio
import base64
import hashlib
import logging
import os
import time
import typing
from dataclasses import dataclass
from functools import lru_cache
from html import escape

import httpx
import yaml
from django.core.cache import cache
from django.http import HttpResponse
from django.views import View


logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class Sponsor:
    """Sponsor information."""

    login: str
    avatar_url: str


class SponsorshipView(View):
    """Handle the funding page request."""

    URL = "https://api.github.com/graphql"
    REPO_URL = (
        "https://api.github.com/repos/{owner}/{repo}/contents/.github/FUNDING.yml"
    )
    FALLBACK_URL = (
        "https://api.github.com/repos/{owner}/.github/contents/.github/FUNDING.yml"
    )
    FALLBACK_ROOT_URL = (
        "https://api.github.com/repos/{owner}/.github/contents/FUNDING.yml"
    )
    QUERY = """
        query($login: String!) {
          user: user(login: $login) {
            login
            avatarUrl
            sponsors(first: 100) {
              nodes {
                ... on User {
                  login
                  avatarUrl
                }
                ... on Organization {
                  login
                  avatarUrl
                }
              }
            }
          }
          organization: organization(login: $login) {
            login
            avatarUrl
            sponsors(first: 100) {
              nodes {
                ... on User {
                  login
                  avatarUrl
                }
                ... on Organization {
                  login
                  avatarUrl
                }
              }
            }
          }
        }
        """
    SIZE = 60
    PADDING = 8
    BORDER_WIDTH = 2
    BUBBLES_PER_LINE = 12
    TTL = 60 * 60 * 24  # 1 day

    headers = {
        "Authorization": f"Bearer {os.getenv('GITHUB_TOKEN')}",
        "Content-Type": "application/json",
    }

    @lru_cache(maxsize=1024)
    async def fetch_user_sponsors(
        self, client: httpx.AsyncClient, login: str
    ) -> list[Sponsor]:
        """Fetch sponsors for a given GitHub login."""
        response = await client.post(
            self.URL,
            headers=self.headers,
            json={"query": self.QUERY, "variables": {"login": login}},
        )
        match response.status_code, response.json():
            case 200, {"data": {"user": {"sponsors": {"nodes": nodes}}}}:
                return [Sponsor(node["login"], node["avatarUrl"]) for node in nodes]
            case 200, {"data": {"organization": {"sponsors": {"nodes": nodes}}}}:
                return [Sponsor(node["login"], node["avatarUrl"]) for node in nodes]
            case _:
                return []

    async def fetch_image(self, client: httpx.AsyncClient, url: str) -> str:
        """Fetch an image and return it as a base64 encoded data URL."""
        cache_key = f"sponsor_avatar_{hashlib.md5(url.encode()).hexdigest()}"
        if data_url := await cache.aget(cache_key):
            return data_url

        try:
            response = await client.get(
                f"{url}&size={self.SIZE * 2}", follow_redirects=True
            )
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "image/png")
            base64_data = base64.b64encode(response.content).decode("utf-8")
            data_url = f"data:{content_type};base64,{base64_data}"
            await cache.aset(cache_key, data_url, self.TTL)
            return data_url
        except httpx.HTTPError as exc:
            logger.error("Failed to fetch image %s: %s", url, exc)
            return url

    async def fetch_repo_sponsors(
        self, client: httpx.AsyncClient, owner: str, repo: str
    ) -> typing.AsyncGenerator[Sponsor, None]:
        """Fetch sponsors from a repository's FUNDING.yml file."""
        urls = [self.REPO_URL.format(owner=owner, repo=repo)]
        if repo != ".github":
            urls.extend(
                [
                    self.FALLBACK_URL.format(owner=owner),
                    self.FALLBACK_ROOT_URL.format(owner=owner),
                ]
            )

        for url in urls:
            response = await client.get(url, headers=self.headers)

            match response.status_code:
                case 200:
                    content = base64.b64decode(response.json()["content"]).decode(
                        "utf-8"
                    )
                    authors = yaml.safe_load(content).get("github", [])
                    if isinstance(authors, list):
                        for author in authors:
                            for sponsor in await self.fetch_user_sponsors(
                                client, author
                            ):
                                yield sponsor
                    else:
                        for sponsor in await self.fetch_user_sponsors(client, authors):
                            yield sponsor
                    return

                case 404:
                    continue

    async def generate_svg(
        self, sponsors: typing.AsyncGenerator[Sponsor], client: httpx.AsyncClient
    ) -> bytes:
        """Generate a single SVG containing all sponsor images."""
        sponsor_list = {sponsor async for sponsor in sponsors}
        match sponsor_list:
            case []:
                return (
                    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 400">'
                    b'<text x="400" y="200" font-size="36" text-anchor="middle" fill="#a9a9a9">No sponsors found yet!</text>'
                    b"</svg>"
                )
            case _:
                pass

        images = await asyncio.gather(
            *(self.fetch_image(client, s.avatar_url) for s in sponsor_list)
        )

        count = len(sponsor_list)
        columns = min(count, self.BUBBLES_PER_LINE)
        rows = (count + self.BUBBLES_PER_LINE - 1) // self.BUBBLES_PER_LINE
        width = columns * (self.SIZE + self.PADDING) + self.PADDING
        height = rows * (self.SIZE + self.PADDING) + self.PADDING

        return "\n".join(
            [
                f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
                "  <defs>",
                '    <clipPath id="circle-clip">',
                f'      <circle cx="{self.SIZE // 2}" cy="{self.SIZE // 2}" r="{self.SIZE // 2}" />',
                "    </clipPath>",
                "  </defs>",
                *(
                    self._generate_bubble(i, s, img)
                    for i, (s, img) in enumerate(zip(sponsor_list, images))
                ),
                "</svg>",
            ]
        ).encode("utf-8")

    def _generate_bubble(self, i: int, sponsor: Sponsor, avatar_data: str) -> str:
        """Generate a single sponsor bubble SVG element."""
        x = self.PADDING + (i % self.BUBBLES_PER_LINE) * (self.SIZE + self.PADDING)
        y = self.PADDING + (i // self.BUBBLES_PER_LINE) * (self.SIZE + self.PADDING)
        return (
            f'  <a href="https://github.com/{escape(sponsor.login)}" target="_blank">'
            f'    <circle cx="{x + self.SIZE // 2}" cy="{y + self.SIZE // 2}" r="{(self.SIZE + self.BORDER_WIDTH) // 2}" '
            f'fill="#fff" stroke="#3333" stroke-width="{self.BORDER_WIDTH}" />'
            f'    <g transform="translate({x}, {y})">'
            f'      <image href="{escape(avatar_data)}" width="{self.SIZE}" height="{self.SIZE}" clip-path="url(#circle-clip)" />'
            f"    </g>"
            "  </a>"
        )

    async def get(self, request, owner: str, repo: str) -> HttpResponse:
        async with httpx.AsyncClient() as client:
            return HttpResponse(
                await self.generate_svg(
                    self.fetch_repo_sponsors(client, owner, repo), client
                ),
                content_type="image/svg+xml",
                headers={
                    "Cache-Control": f"public, max-age={self.TTL}",
                    "Max-Age": time.strftime(
                        "%a, %d %b %Y GMT", time.gmtime(time.time() + self.TTL)
                    ),
                },
            )
