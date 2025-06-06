from scholarly import scholarly, ProxyGenerator
import difflib
import time
from functools import wraps
import signal
import random

def timeout_handler(signum, frame):
    raise TimeoutError("Operation timed out")

def timeout(seconds):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Set the signal handler and a timeout
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(seconds)
            try:
                result = func(*args, **kwargs)
            finally:
                # Disable the alarm
                signal.alarm(0)
            return result
        return wrapper
    return decorator

def safe_next(iterator, timeout_secs=5):
    """Safely get next item from iterator with timeout"""
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(timeout_secs)
    try:
        item = next(iterator)
        signal.alarm(0)
        return item
    except StopIteration:
        signal.alarm(0)
        raise
    except TimeoutError:
        signal.alarm(0)
        raise TimeoutError(f"Iterator next() operation timed out after {timeout_secs} seconds")
    except Exception as e:
        signal.alarm(0)
        raise

def retry_with_delay(func, max_retries=3, base_delay=1):
    """Retry a function with exponential backoff"""
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
            print(f"[DEBUG] Attempt {attempt + 1} failed, retrying in {delay:.2f} seconds...")
            time.sleep(delay)

def search_for_author_exact_match(author_name, similarity_threshold=0.8):
    print(f"[DEBUG] Starting search_for_author_exact_match for author: {author_name}")
    
    # Try to set up proxy but don't fail if it doesn't work
    proxy_setup_success = False
    try:
        pg = ProxyGenerator()
        # Try different proxy methods
        proxy_methods = [
            lambda: pg.FreeProxies(),
            lambda: pg.Tor_External(tor_sock_port=9050, tor_control_port=9051),
            lambda: pg.ScraperAPI('YOUR_API_KEY')  # Only if you have a key
        ]
        
        for method in proxy_methods:
            try:
                success = method()
                if success:
                    scholarly.use_proxy(pg)
                    print("[DEBUG] Successfully set up proxy")
                    proxy_setup_success = True
                    break
            except Exception as e:
                print(f"[DEBUG] Proxy method failed: {str(e)}")
                continue
                
        if not proxy_setup_success:
            print("[DEBUG] All proxy setup methods failed, continuing without proxy")
            
    except Exception as e:
        print(f"[DEBUG] Error in proxy setup: {str(e)}")
    
    def perform_author_search():
        try:
            print("[DEBUG] Initiating scholarly.search_author")
            search_query = scholarly.search_author(author_name)
            print("[DEBUG] Successfully created search_query object")
            
            authors_found = 0
            max_authors_to_check = 5
            
            while authors_found < max_authors_to_check:
                try:
                    print(f"[DEBUG] Attempting to fetch author {authors_found + 1}/{max_authors_to_check}")
                    potential_author = safe_next(search_query, timeout_secs=20)  # Increased timeout
                    authors_found += 1
                    
                    if not potential_author:
                        print("[DEBUG] Received empty author data")
                        continue
                        
                    print(f"[DEBUG] Processing potential author: {potential_author.get('name', 'Unknown')}")
                    found_name = potential_author.get('name', '')
                    if not found_name:
                        print("[DEBUG] Author name missing in data")
                        continue
                        
                    similarity = difflib.SequenceMatcher(None, author_name.lower(), found_name.lower()).ratio()
                    print(f"[DEBUG] Similarity score: {similarity} for author: {found_name}")
                    
                    if similarity >= similarity_threshold:
                        print(f"[DEBUG] Found matching author with similarity {similarity}. Filling author data...")
                        try:
                            filled_author = scholarly.fill(potential_author, sections=['publications'])
                            print("[DEBUG] Successfully filled author data")
                            return filled_author
                        except Exception as e:
                            print(f"[DEBUG] Error filling author data: {str(e)}")
                            # Try next author instead of breaking immediately
                            continue
                    
                except TimeoutError as te:
                    print(f"[DEBUG] Timeout while fetching author: {str(te)}")
                    time.sleep(2)  # Add delay before next attempt
                    continue
                except StopIteration:
                    print("[DEBUG] No more authors to process")
                    break
                except Exception as e:
                    print(f"[DEBUG] Error processing author: {str(e)}")
                    time.sleep(1)  # Add delay before next attempt
                    continue
            
            return None
            
        except Exception as e:
            print(f"[DEBUG] Error in author search: {str(e)}")
            return None

    try:
        # Try the author search with retries
        author_result = retry_with_delay(perform_author_search, max_retries=3, base_delay=2)
        
        if author_result:
            return author_result
            
        # If author search fails, try publication search
        print(f"[DEBUG] No exact author match found for {author_name}. Performing keyword search...")
        keyword_search_results = []
        
        def perform_pub_search():
            try:
                print("[DEBUG] Initiating scholarly.search_pubs")
                search_query = scholarly.search_pubs(author_name)
                results = []
                
                for i in range(3):
                    try:
                        print(f"[DEBUG] Fetching publication {i+1}/3")
                        pub = safe_next(search_query, timeout_secs=15)
                        if pub and 'bib' in pub and 'title' in pub['bib']:
                            print(f"[DEBUG] Found valid publication: {pub['bib']['title']}")
                            results.append(pub)
                    except (TimeoutError, StopIteration):
                        break
                return results
            except Exception as e:
                print(f"[DEBUG] Error in publication search: {str(e)}")
                return []

        # Try the publication search with retries
        keyword_search_results = retry_with_delay(perform_pub_search, max_retries=2, base_delay=1)
        
        print(f"[DEBUG] Found {len(keyword_search_results)} publications in keyword search")
        publication_titles = [pub['bib']['title'] for pub in keyword_search_results if 'bib' in pub and 'title' in pub['bib']]
        print(f"[DEBUG] Extracted {len(publication_titles)} publication titles")
        
        return {'name': author_name, 'publications': publication_titles}
        
    except Exception as e:
        print(f"[DEBUG] Critical error in search_for_author_exact_match: {str(e)}")
        return {'name': author_name, 'publications': []}

def get_top_cited_and_recent_papers(author_profile, top_recent=4, top_cited=1):
    if author_profile and 'publications' in author_profile:
        # Filter valid publications with valid dictionaries
        valid_publications = [pub for pub in author_profile['publications'] if isinstance(pub, dict)]
        
        # Extract papers with valid publish dates and sort by the most recent
        recent_publications = [
            pub for pub in valid_publications if 'pub_year' in pub.get('bib', {}) and pub['bib']['pub_year'].isdigit()
        ]
        recent_publications = sorted(recent_publications, key=lambda x: int(x['bib']['pub_year']), reverse=True)
        
        # Select top N recent papers
        top_recent_publications = recent_publications[:top_recent]
        
        # Sort all valid publications by the most cited
        sorted_by_citations = sorted(valid_publications, key=lambda x: x.get('num_citations', 0), reverse=True)
        
        # Select top M most cited papers
        top_cited_publications = sorted_by_citations[:top_cited]
        
        # Combine the results, ensuring no duplicates
        unique_publications = {pub['bib']['title']: pub for pub in top_recent_publications + top_cited_publications}
        combined_publications = list(unique_publications.values())
        
        # Format the result as a list of (title, citations, year)
        return [
            (
                pub['bib']['title'],
                pub.get('num_citations', ''),
                pub['bib'].get('pub_year', 'N/A')
            )
            for pub in combined_publications if 'bib' in pub and 'title' in pub['bib']
        ]
    else:
        return []

#professor_name = "Ronald N. Goldman"
#author_profile = search_for_author_exact_match(professor_name)

#text_from_scholarly = " "

#if author_profile:
#    top_cited_papers = get_top_cited_papers(author_profile)
#    for title, citations in top_cited_papers:
#        text_from_scholarly += f"Title: {title}, Citations: {citations}\n"
#else:
#    text_from_scholarly = "Not available, replace this with information from google scrape"