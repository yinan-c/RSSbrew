import re
from bs4 import BeautifulSoup
import logging
from urllib.parse import urlparse, urlunparse

logger = logging.getLogger('feed_logger')

def clean_url(url):
    parsed_url = urlparse(url)
    # 重建 URL，不包括片段和查询字符串
    clean_url = urlunparse((parsed_url.scheme, parsed_url.netloc, parsed_url.path.rstrip('/'), '', '', ''))
    # 转换为小写
    clean_url = clean_url.lower()
    return clean_url

def clean_html(html_content):
    """
    This function is used to clean the HTML content.
    It will remove all the <script>, <style>, <img>, <a>, <video>, <audio>, <iframe>, <input> tags.
    Returns:
        Cleaned text for summarization
    """
    soup = BeautifulSoup(html_content, "html.parser")

    for script in soup.find_all("script"):
        script.decompose()

    for style in soup.find_all("style"):
        style.decompose()

    for img in soup.find_all("img"):
        img.decompose()

    for a in soup.find_all("a"):
        a.decompose()

    for video in soup.find_all("video"):
        video.decompose()

    for audio in soup.find_all("audio"):
        audio.decompose()
    
    for iframe in soup.find_all("iframe"):
        iframe.decompose()
    
    for input in soup.find_all("input"):
        input.decompose()

    return soup.get_text()

def generate_untitled(entry):
    try: return entry.title
    except: 
        try: return entry.article[:50]
        except: return entry.link

def passes_filters(entry, feed, filter_type):
    # if there are no filters, return True
    if not feed.filters.filter(usage=filter_type).exists():
        return True
    filter_relational_operator = feed.filter_relational_operator
    results = []
    for filter in feed.filters.filter(usage=filter_type):
        if filter.field == 'title':
            content = generate_untitled(entry)
        elif filter.field == 'content':
            try:
                content = entry.content[0].value
            except:
                content = entry.description
            finally:
                content = entry.content if hasattr(entry, 'content') else ''

        elif filter.field == 'link':
            content = entry.url
        if match_content(content, filter):
#            logger.info(f"  Filter {filter_type}, Entry {entry.title} passed filter {filter}")
            results.append(True)
        else:
            results.append(False)

    if filter_relational_operator == 'all':
        if all(results):
            return True
        else:
            logger.info(f"  Filter {filter_type}, Entry {entry.title} did not pass all filters")
            return False
    elif filter_relational_operator == 'any':
        if any(results):
            return True
        else:
            logger.info(f"  Filter {filter_type}, Entry {entry.title} did not pass any filters")
            return False
    elif filter_relational_operator == 'none':
        if not any(results):
            return True
        else:
            logger.info(f"  Filter {filter_type}, Entry {entry.title} passed at least one filter")
            return False

def match_content(content, filter):
    if filter.match_type == 'contains':
        return filter.value in content
    elif filter.match_type == 'does_not_contain':
        return filter.value not in content
    elif filter.match_type == 'matches_regex':
        return re.search(filter.value, content) is not None
    elif filter.match_type == 'does_not_match_regex':
        return re.search(filter.value, content) is None
    elif filter.match_type == 'shorter_than':
        return len(content) < int(filter.value)
    elif filter.match_type == 'longer_than':
        return len(content) > int(filter.value)