import logging
import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from lxml import html


class LinkParser:
    """Tool class parses URL."""

    @staticmethod
    def parse_input_url(url: str) -> tuple[list[str], int]:
        parsed_url = urlparse(url)
        path_parts = parsed_url.path.split("/")
        query_params = parse_qs(parsed_url.query)
        start_page: int = int(query_params.get("page", [1])[0])  # default page=1
        return path_parts, start_page

    @staticmethod
    def parse_html(html_content: str, logger: logging.Logger) -> html.HtmlElement | None:
        if "Failed" in html_content:
            return None

        try:
            return html.fromstring(html_content)
        except Exception as e:
            logger.error("Error parsing HTML content: %s", e)
            return None

    @staticmethod
    def get_max_page(tree: html.HtmlElement) -> int:
        """Parse pagination count."""
        page_links = tree.xpath(
            '//li[@class="page-item"]/a[@class="page-link" and string-length(text()) <= 2]/@href'
        )

        if not page_links:
            return 1

        page_numbers = []
        for link in page_links:
            match = re.search(r"page=(\d+)", link)
            if match:
                page_number = int(match.group(1))
            else:
                page_number = 1
            page_numbers.append(page_number)

        return max(page_numbers)

    @staticmethod
    def add_page_num(url: str, page: int) -> str:
        parsed_url = urlparse(url)  # 解析 URL
        query_params = parse_qs(parsed_url.query)  # 解析查詢參數
        query_params["page"] = [str(page)]  # 修改頁碼

        new_query = urlencode(query_params, doseq=True)  # 組合成字串
        new_url = parsed_url._replace(query=new_query)  # 替換頁碼

        # Example
        # url = "https://example.com/search?q=test&sort=asc", page = 3
        # parsed_url: ParseResult(scheme='https', netloc='example.com', path='/search', params='', query='q=test&sort=asc', fragment='')
        # query_params: {'q': ['test'], 'sort': ['asc'], 'page': ['3']}
        # new_query: 'q=test&sort=asc&page=3'
        # new_url: ParseResult(scheme='https', netloc='example.com', path='/search', params='', query='q=test&sort=asc&page=3', fragment='')
        # urlunparse: 'https://example.com/search?q=test&sort=asc&page=3'
        return urlunparse(new_url)

    @staticmethod
    def remove_page_num(url: str) -> str:
        """remove ?page=d or &page=d from URL."""
        # Parse the URL
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)

        # Remove the 'page' parameter if it exists
        if "page" in query_params:
            del query_params["page"]

        # Rebuild the query string without 'page'
        new_query = urlencode(query_params, doseq=True)

        # Rebuild the full URL
        new_url = urlunparse(parsed_url._replace(query=new_query))
        return new_url
